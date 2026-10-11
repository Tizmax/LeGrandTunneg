"""Moteur de règles orchestré — miroir exact de frontend/src/game/gameReducer.ts,
augmenté de l'enforcement des rôles/permissions décrit dans
docs/websocket-protocol.md (table "messages client → serveur").

Module Python pur, découplé de tout transport : réutilisé tel quel par le
handler WebSocket (Bloc 5) et par le futur mode room solo hotseat (Bloc 7bis).
Chaque fonction prend l'état courant + les paramètres de l'action, renvoie un
nouvel état (immuable), et lève `GameError` si l'action est refusée (rôle
incorrect, mauvais tour, phase incompatible, payload invalide) — à charge du
code appelant (handler WS) de traduire `GameError` en message `error` du
protocole sans modifier l'état ni diffuser de broadcast.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Literal

from .rules import coffrer, create_theme, poursuivre, reset_theme
from .types import GameState, HistoryEntry, Player, Theme

Role = Literal["presentateur", "joueur", "ecran-principal"]

ErrorCode = Literal[
    "forbidden_role",
    "not_your_turn",
    "invalid_phase",
    "invalid_payload",
]


class GameError(Exception):
    """Erreur de règle de jeu — correspond au message `error` du protocole WS."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


# --- Helpers internes ------------------------------------------------------


def _require_role(actor_role: Role, required: Role) -> None:
    if actor_role != required:
        raise GameError(
            "forbidden_role",
            f"Action réservée au rôle '{required}' (reçu '{actor_role}').",
        )


def _require_current_player(
    state: GameState, actor_role: Role, actor_player_id: str
) -> None:
    if actor_role != "joueur":
        raise GameError("forbidden_role", "Action réservée au joueur concerné.")
    if not state.players:
        raise GameError("invalid_phase", "Aucun joueur dans la partie.")
    current = state.players[state.current_player_index]
    if current.id != actor_player_id:
        raise GameError(
            "not_your_turn", "Ce n'est pas le tour de ce joueur."
        )


def _next_player_index(players: tuple[Player, ...], current: int) -> int:
    """Avance au joueur suivant dans l'ordre fixe, en SAUTANT les joueurs
    déconnectés (voir `set_player_connected`) : un joueur parti reste dans
    `players` (classement final) mais son tour ne lui est plus proposé tant
    qu'il n'est pas revenu. Si personne n'est connecté (cas limite), on
    avance quand même d'un cran pour ne jamais bloquer le moteur."""
    count = len(players)
    if count == 0:
        return 0
    for step in range(1, count + 1):
        idx = (current + step) % count
        if players[idx].connected:
            return idx
    return (current + 1) % count


def _credit_points(
    players: tuple[Player, ...], index: int, amount: int
) -> tuple[Player, ...]:
    if amount <= 0:
        return players
    return tuple(
        replace(p, points=p.points + amount) if i == index else p
        for i, p in enumerate(players)
    )


def _all_themes_completed(themes: tuple[Theme, ...]) -> bool:
    return len(themes) > 0 and all(t.completed for t in themes)


def _record_coffrage(
    state: GameState,
    theme_label: str,
    points_gained: int,
) -> tuple[Player, ...]:
    """Retourne l'historique à jour (append si des points ont été gagnés)."""
    if points_gained <= 0:
        return state.history
    return state.history + (
        HistoryEntry(
            theme_label=theme_label,
            player_name=state.players[state.current_player_index].name,
            points_gained=points_gained,
        ),
    )


# --- Lobby : joueurs, thèmes, renommage --------------------------------------
#
# Fusion 2026-10-11 : les anciennes phases 'menu' (attente joueurs) et
# 'themes' (saisie des thèmes) sont unifiées en une seule phase 'lobby' —
# tout se passe sur le même écran (liste des joueurs, saisie des thèmes par
# le Présentateur, renommage de soi), et `game:start` combine les deux
# anciennes préconditions (>=2 joueurs, >=1 thème). Le message
# `lobby:go_to_themes` / l'action `GO_TO_THEMES` n'existent plus.


def add_player(state: GameState, player_id: str, name: str) -> GameState:
    """Appelé par la couche REST (jointure de room), pas par un message WS."""
    name = name.strip()
    if not name:
        raise GameError("invalid_payload", "Le pseudo ne peut pas être vide.")
    if state.phase != "lobby":
        raise GameError(
            "invalid_phase", "Impossible de rejoindre une partie déjà lancée."
        )
    return replace(
        state, players=state.players + (Player(id=player_id, name=name),)
    )


def remove_player(state: GameState, index: int, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "Le lobby est clos.")
    if not (0 <= index < len(state.players)):
        raise GameError("invalid_payload", "Index de joueur invalide.")
    return replace(
        state,
        players=tuple(p for i, p in enumerate(state.players) if i != index),
    )


def rename_player(
    state: GameState, actor_role: Role, actor_player_id: str, name: str
) -> GameState:
    """Un joueur renomme UNIQUEMENT lui-même, possible seulement en lobby.

    Le renommage du Présentateur et de l'Écran principal (qui n'apparaissent
    jamais dans `state.players`) est géré hors de ce module, directement au
    niveau de `app.rooms.manager.Room.names` par le handler WS."""
    _require_role(actor_role, "joueur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "Le renommage n'est possible qu'en lobby.")
    name = name.strip()
    if not name:
        raise GameError("invalid_payload", "Le pseudo ne peut pas être vide.")
    index = next(
        (i for i, p in enumerate(state.players) if p.id == actor_player_id), None
    )
    if index is None:
        raise GameError("invalid_payload", "Joueur introuvable dans la partie.")
    players = tuple(
        replace(p, name=name) if i == index else p
        for i, p in enumerate(state.players)
    )
    return replace(state, players=players)


def add_theme(state: GameState, label: str, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "La saisie des thèmes est close.")
    label = label.strip()
    if not label:
        raise GameError("invalid_payload", "Le thème ne peut pas être vide.")
    return replace(state, themes=state.themes + (create_theme(label),))


def remove_theme(state: GameState, index: int, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "La saisie des thèmes est close.")
    if not (0 <= index < len(state.themes)):
        raise GameError("invalid_payload", "Index de thème invalide.")
    return replace(
        state,
        themes=tuple(t for i, t in enumerate(state.themes) if i != index),
    )


def start_game(
    state: GameState, actor_role: Role, rng: random.Random | None = None
) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "La partie a déjà démarré.")
    if len(state.players) < 2:
        raise GameError("invalid_payload", "Minimum 2 joueurs requis.")
    if len(state.themes) < 1:
        raise GameError("invalid_payload", "Minimum 1 thème requis.")
    rng = rng or random
    start_index = rng.randrange(len(state.players))
    return replace(
        state,
        phase="selection-pending",
        current_player_index=start_index,
        active_theme_index=None,
        tunnel_sub_phase=None,
        history=(),
    )


# --- Couche show : révélation des choix joueur ------------------------------


def reveal_choice(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase == "selection-pending":
        return replace(state, phase="selection")
    if state.tunnel_sub_phase == "after-success-pending":
        return replace(state, tunnel_sub_phase="after-success-open")
    raise GameError(
        "invalid_phase", "Aucun choix joueur en attente de révélation."
    )


# --- Sélection de thème ------------------------------------------------------


def select_theme(
    state: GameState, index: int, actor_role: Role, actor_player_id: str
) -> GameState:
    if state.phase != "selection":
        raise GameError(
            "invalid_phase", "Le choix de thème n'est pas encore révélé."
        )
    _require_current_player(state, actor_role, actor_player_id)
    if not (0 <= index < len(state.themes)):
        raise GameError("invalid_payload", "Index de thème invalide.")
    theme = state.themes[index]
    if theme.completed:
        raise GameError("invalid_payload", "Ce thème est déjà coffré en totalité.")
    themes = tuple(
        replace(t, discovered=True) if i == index else t
        for i, t in enumerate(state.themes)
    )
    return replace(
        state,
        phase="tunnel",
        themes=themes,
        active_theme_index=index,
        tunnel_sub_phase="question-pending",
    )


# --- Lancement du chrono (Présentateur) --------------------------------------


def start_timer(state: GameState, actor_role: Role) -> GameState:
    """Le Présentateur a fini de poser sa question à l'oral et déclenche le
    chrono : question-pending -> question. Avant cet appel, le joueur
    concerné voit un écran "écoute la question" sans minuteur ; après, le
    jugement (Bonne/Mauvaise réponse/Passer) devient possible."""
    _require_role(actor_role, "presentateur")
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question-pending":
        raise GameError("invalid_phase", "Aucune question en attente de lancement du chrono.")
    return replace(state, tunnel_sub_phase="question")


# --- Jugement de la réponse orale (Présentateur) -----------------------------


def good_answer(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question":
        raise GameError("invalid_phase", "Aucune question en cours à juger.")
    idx = state.active_theme_index
    assert idx is not None
    theme = state.themes[idx]
    discovered_false = replace(theme, discovered=False)
    result = poursuivre(discovered_false)
    themes = tuple(
        result.theme if i == idx else t for i, t in enumerate(state.themes)
    )

    if result.auto_coffrage:
        players = _credit_points(
            state.players, state.current_player_index, result.points_gained
        )
        history = _record_coffrage(state, theme.label, result.points_gained)
        completed = _all_themes_completed(themes)
        return replace(
            state,
            themes=themes,
            players=players,
            history=history,
            current_player_index=_next_player_index(
                state.players, state.current_player_index
            ),
            phase="end" if completed else "selection-pending",
            active_theme_index=None,
            tunnel_sub_phase=None,
        )

    return replace(state, themes=themes, tunnel_sub_phase="after-success-pending")


def bad_answer(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question":
        raise GameError("invalid_phase", "Aucune question en cours à juger.")
    return replace(
        state,
        phase="selection-pending",
        active_theme_index=None,
        tunnel_sub_phase=None,
        current_player_index=_next_player_index(
            state.players, state.current_player_index
        ),
    )


def pass_question(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question":
        raise GameError("invalid_phase", "Aucune question en cours à juger.")
    idx = state.active_theme_index
    assert idx is not None
    theme = state.themes[idx]
    nullified_square = theme.progress_value + 1
    theme_with_nullified = replace(
        theme, nullified=theme.nullified + (nullified_square,)
    )
    result = poursuivre(theme_with_nullified)
    themes = tuple(
        result.theme if i == idx else t for i, t in enumerate(state.themes)
    )

    if result.auto_coffrage:
        players = _credit_points(
            state.players, state.current_player_index, result.points_gained
        )
        history = _record_coffrage(state, theme.label, result.points_gained)
        completed = _all_themes_completed(themes)
        return replace(
            state,
            themes=themes,
            players=players,
            history=history,
            # Passer : le joueur courant ne change PAS, même en cas de
            # coffrage automatique (cf spécification figée).
            phase="end" if completed else "selection-pending",
            active_theme_index=None,
            tunnel_sub_phase=None,
        )

    return replace(
        state,
        phase="selection-pending",
        themes=themes,
        active_theme_index=None,
        tunnel_sub_phase=None,
        # current_player_index inchangé : le joueur reste actif.
    )


# --- Choix Continuer / Coffrer (joueur concerné) ----------------------------


def continue_tunnel(
    state: GameState, actor_role: Role, actor_player_id: str
) -> GameState:
    _require_current_player(state, actor_role, actor_player_id)
    if state.active_theme_index is None or state.tunnel_sub_phase != "after-success-open":
        raise GameError("invalid_phase", "Le choix Continuer/Coffrer n'est pas ouvert.")
    idx = state.active_theme_index
    themes = tuple(
        replace(t, discovered=True) if i == idx else t
        for i, t in enumerate(state.themes)
    )
    return replace(state, themes=themes, tunnel_sub_phase="question-pending")


def vault(state: GameState, actor_role: Role, actor_player_id: str) -> GameState:
    """Action "Coffrer" déclenchée manuellement par le joueur (answer:vault)."""
    _require_current_player(state, actor_role, actor_player_id)
    if state.active_theme_index is None or state.tunnel_sub_phase != "after-success-open":
        raise GameError("invalid_phase", "Le choix Continuer/Coffrer n'est pas ouvert.")
    idx = state.active_theme_index
    theme = state.themes[idx]
    result = coffrer(theme)
    themes = tuple(
        result.theme if i == idx else t for i, t in enumerate(state.themes)
    )
    players = _credit_points(
        state.players, state.current_player_index, result.points_gained
    )
    history = _record_coffrage(state, theme.label, result.points_gained)
    completed = _all_themes_completed(themes)
    return replace(
        state,
        themes=themes,
        players=players,
        history=history,
        phase="end" if completed else "selection-pending",
        active_theme_index=None,
        tunnel_sub_phase=None,
        current_player_index=_next_player_index(
            state.players, state.current_player_index
        ),
    )


# --- Présence / absence d'un joueur (connexion WS individuelle) -------------
#
# Un joueur qui ferme son onglet ou perd sa connexion n'est PAS retiré de la
# partie : il reste dans `state.players` (visible, conserve ses points pour
# le classement final), seul son tour est sauté (voir `_next_player_index`).
# S'il se reconnecte (même local_player_id), il redevient `connected` et
# reprend sa place normalement, y compris son tour s'il retombe dessus —
# aucun rattrapage automatique des tours manqués.


def set_player_connected(state: GameState, player_id: str, connected: bool) -> GameState:
    index = next((i for i, p in enumerate(state.players) if p.id == player_id), None)
    if index is None:
        return state
    if state.players[index].connected == connected:
        return state
    players = tuple(
        replace(p, connected=connected) if i == index else p
        for i, p in enumerate(state.players)
    )
    return replace(state, players=players)


# --- Fin de partie anticipée (Présentateur) ----------------------------------


def end_game_early(state: GameState, actor_role: Role) -> GameState:
    """Le Présentateur met fin à la partie en cours à tout moment et ramène
    tout le monde au lobby — joueurs et thèmes conservés (pour relancer
    rapidement), scores et progression remis à zéro, comme `reset_game` mais
    vers 'lobby' plutôt que de relancer directement une sélection."""
    _require_role(actor_role, "presentateur")
    return replace(
        state,
        # `connected` n'est PAS réinitialisé ici : reflète la vraie connexion
        # WS en cours, gérée uniquement par `set_player_connected`.
        players=tuple(replace(p, points=0) for p in state.players),
        themes=tuple(reset_theme(t) for t in state.themes),
        current_player_index=0,
        active_theme_index=None,
        tunnel_sub_phase=None,
        history=(),
        phase="lobby",
    )


# --- Reset / quitter ---------------------------------------------------------


def reset_game(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    return replace(
        state,
        players=tuple(replace(p, points=0) for p in state.players),
        themes=tuple(reset_theme(t) for t in state.themes),
        current_player_index=0,
        active_theme_index=None,
        tunnel_sub_phase=None,
        history=(),
        phase="selection-pending",
    )


def quit_to_menu(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    return GameState()


__all__ = [
    "Role",
    "ErrorCode",
    "GameError",
    "add_player",
    "remove_player",
    "rename_player",
    "add_theme",
    "remove_theme",
    "start_game",
    "reveal_choice",
    "select_theme",
    "start_timer",
    "good_answer",
    "bad_answer",
    "pass_question",
    "continue_tunnel",
    "vault",
    "set_player_connected",
    "end_game_early",
    "reset_game",
    "quit_to_menu",
]
