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

from app.core.settings import settings

from .rules import coffrer, create_theme, poursuivre, reset_theme
from .types import GameState, HistoryEntry, Player, Theme

Role = Literal["presentateur", "joueur", "ecran-principal"]

ErrorCode = Literal[
    "forbidden_role",
    "not_your_turn",
    "invalid_phase",
    "invalid_payload",
    "game_suspended",
    "capacity_exceeded",
    "rate_limited",
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


def _require_presenter(state: GameState, actor_player_id: str) -> None:
    """Vérifie que l'acteur est bien le présentateur (is_presenter=True dans players)."""
    player = next((p for p in state.players if p.id == actor_player_id), None)
    if player is None or not player.is_presenter:
        raise GameError("forbidden_role", "Action réservée au Présentateur.")


# IDs des avatars SVG embarqués dans frontend/public/avatars/{id}.svg
# (DiceBear Lorelei, seeds fixes, licence CC0)
_ALLOWED_AVATARS: list[str] = [
    "alice", "bob", "charlie", "diana", "edgar", "flora",
    "gareth", "hannah", "ivan", "julia", "kevin", "luna",
    "marco", "nina", "oscar", "petra",
]
_ALLOWED_AVATARS_SET: frozenset[str] = frozenset(_ALLOWED_AVATARS)

def _taken_avatars(state: GameState) -> set[str]:
    """Retourne l'ensemble des avatars déjà assignés dans la room."""
    return {p.avatar for p in state.players if p.avatar}


def pick_random_avatar(state: GameState) -> str:
    """Tire au sort un avatar libre (non pris par un autre participant).
    Retombe sur n'importe quel avatar autorisé si tous sont pris (cas limite)."""
    taken = _taken_avatars(state)
    free = [a for a in _ALLOWED_AVATARS if a not in taken]
    pool = free if free else _ALLOWED_AVATARS
    return random.choice(pool)


def set_player_avatar(
    state: GameState, actor_player_id: str, avatar: str
) -> GameState:
    """Change l'avatar d'un participant (joueur ou présentateur) en lobby.
    Vérifie que l'avatar est autorisé et non déjà pris par un autre."""
    if not any(p.id == actor_player_id for p in state.players):
        raise GameError("forbidden_role", "Action réservée aux participants.")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "L'avatar ne peut être changé qu'en lobby.")
    if avatar not in _ALLOWED_AVATARS_SET:
        raise GameError("invalid_payload", f"Avatar non autorisé : {avatar!r}")
    # Vérifie que personne d'autre n'a déjà cet avatar
    for p in state.players:
        if p.avatar == avatar and p.id != actor_player_id:
            raise GameError("invalid_payload", f"Cet avatar est déjà pris.")
    new_players = tuple(
        replace(p, avatar=avatar) if p.id == actor_player_id else p
        for p in state.players
    )
    return replace(state, players=new_players)


def _require_current_player(
    state: GameState, actor_role: Role, actor_player_id: str
) -> None:
    _require_role(actor_role, "joueur")
    _require_playable_turn(state)
    # Le présentateur ne peut pas jouer son propre tour
    actor = next((p for p in state.players if p.id == actor_player_id), None)
    if actor is None or actor.is_presenter:
        raise GameError("forbidden_role", "Action réservée au joueur concerné.")
    joueurs = [p for p in state.players if not p.is_presenter]
    if not joueurs:
        raise GameError("invalid_phase", "Aucun joueur dans la partie.")
    if state.current_player_index is None:
        raise GameError("invalid_phase", "Aucun tour en cours.")
    current = state.players[state.current_player_index]
    if current.id != actor_player_id:
        raise GameError(
            "not_your_turn", "Ce n'est pas le tour de ce joueur."
        )


def _require_playable_turn(state: GameState) -> None:
    if state.turn_status in ("active-absent", "waiting-eligible"):
        raise GameError("game_suspended", "La partie attend un joueur connecté.")


def _next_player_index(players: tuple[Player, ...], current: int) -> int | None:
    """Avance au joueur suivant dans l'ordre fixe, en SAUTANT les joueurs
    déconnectés ET le présentateur (qui n'a pas de tour). Un joueur parti
    reste dans `players` (classement final) mais son tour est sauté tant
    qu'il n'est pas revenu. Aucun joueur éligible donne None."""
    count = len(players)
    if count == 0:
        return None
    for step in range(1, count + 1):
        idx = (current + step) % count
        if players[idx].connected and not players[idx].is_presenter:
            return idx
    return None


def _finish_turn(state: GameState, *, rotate: bool = True) -> GameState:
    """Termine une transition acceptée, sans inventer d'acteur de secours."""
    if _all_themes_completed(state.themes):
        return replace(
            state, phase="end", current_player_index=None,
            turn_status="idle", rotation_anchor_index=None,
            active_theme_index=None, tunnel_sub_phase=None,
        )
    departing = state.current_player_index
    assert departing is not None
    current = _next_player_index(state.players, departing) if rotate else departing
    return replace(
        state, phase="selection-pending", current_player_index=current,
        turn_status="waiting-eligible" if current is None else "ready",
        rotation_anchor_index=departing if current is None else None,
        active_theme_index=None, tunnel_sub_phase=None,
    )


def _credit_points(
    players: tuple[Player, ...], index: int | None, amount: int
) -> tuple[Player, ...]:
    if amount <= 0 or index is None:
        return players
    return tuple(
        replace(p, points=p.points + amount) if i == index and not p.is_presenter else p
        for i, p in enumerate(players)
    )


def _all_themes_completed(themes: tuple[Theme, ...]) -> bool:
    return len(themes) > 0 and all(t.completed for t in themes)


def _record_coffrage(
    state: GameState,
    theme_label: str,
    points_gained: int,
) -> tuple[HistoryEntry, ...]:
    """Retourne l'historique à jour (append si des points ont été gagnés)."""
    if points_gained <= 0:
        return state.history
    assert state.current_player_index is not None
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


def add_player(
    state: GameState,
    player_id: str,
    name: str,
    is_presenter: bool = False,
    avatar: str = "",
) -> GameState:
    """Appelé par la couche REST (jointure de room), pas par un message WS.

    Si `avatar` est vide, tire au sort un avatar libre automatiquement.
    La limite configurée s'applique au total (présentateur inclus)."""
    name = name.strip()
    if not name or len(name) > settings.max_name_chars:
        raise GameError("invalid_payload", "Le pseudo ne peut pas être vide.")
    if state.phase != "lobby":
        raise GameError(
            "invalid_phase", "Impossible de rejoindre une partie déjà lancée."
        )
    if len(state.players) >= settings.max_players:
        raise GameError(
            "capacity_exceeded",
            f"La room est pleine (maximum {settings.max_players} participants).",
        )
    chosen_avatar = avatar if avatar in _ALLOWED_AVATARS_SET else pick_random_avatar(state)
    return replace(
        state,
        players=state.players + (
            Player(id=player_id, name=name, avatar=chosen_avatar, is_presenter=is_presenter),
        ),
    )


def remove_player(state: GameState, index: int, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "Le lobby est clos.")
    if type(index) is not int or not (0 <= index < len(state.players)):
        raise GameError("invalid_payload", "Index de joueur invalide.")
    if state.players[index].is_presenter:
        raise GameError("invalid_payload", "Impossible de retirer le Présentateur.")
    return replace(
        state,
        players=tuple(p for i, p in enumerate(state.players) if i != index),
    )


def transfer_presenter(state: GameState, target_player_id: str, actor_role: Role) -> GameState:
    """Transfère le rôle Présentateur à un joueur existant dans le lobby.

    Met à jour is_presenter sur les deux joueurs concernés dans state.players.
    Les champs room.roles et room.presentateur_id sont mis à jour par ws.py.
    """
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "Le transfert de Présentateur n'est possible qu'en lobby.")
    # Trouver l'actuel présentateur et la cible
    current_presenter = next((p for p in state.players if p.is_presenter), None)
    target = next((p for p in state.players if p.id == target_player_id), None)
    if target is None:
        raise GameError("invalid_payload", "Joueur cible introuvable.")
    if target.is_presenter:
        raise GameError("invalid_payload", "Ce joueur est déjà le Présentateur.")
    new_players = tuple(
        replace(p, is_presenter=(p.id == target_player_id))
        if p.id == target_player_id or (current_presenter and p.id == current_presenter.id)
        else p
        for p in state.players
    )
    return replace(state, players=new_players)


def rename_player(
    state: GameState, actor_role: Role, actor_player_id: str, name: str
) -> GameState:
    """Tout participant (joueur ou présentateur) renomme UNIQUEMENT lui-même,
    possible seulement en lobby."""
    if actor_role == "ecran-principal":
        raise GameError("forbidden_role", "Action réservée aux participants.")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "Le renommage n'est possible qu'en lobby.")
    name = name.strip()
    if not name or len(name) > settings.max_name_chars:
        raise GameError("invalid_payload", "Le pseudo ne peut pas être vide.")
    index = next(
        (i for i, p in enumerate(state.players) if p.id == actor_player_id), None
    )
    if index is None:
        raise GameError("invalid_payload", "Participant introuvable dans la partie.")
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
    if not label or len(label) > settings.max_theme_label_chars:
        raise GameError("invalid_payload", "Le thème ne peut pas être vide.")
    if len(state.themes) >= settings.max_themes:
        raise GameError("capacity_exceeded", "Le nombre maximal de thèmes est atteint.")
    return replace(state, themes=state.themes + (create_theme(label),))


def remove_theme(state: GameState, index: int, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "La saisie des thèmes est close.")
    if type(index) is not int or not (0 <= index < len(state.themes)):
        raise GameError("invalid_payload", "Index de thème invalide.")
    return replace(
        state,
        themes=tuple(t for i, t in enumerate(state.themes) if i != index),
    )


def start_game(
    state: GameState, actor_role: Role, actor_player_id: str = "", rng: random.Random | None = None
) -> GameState:
    _require_role(actor_role, "presentateur")
    if state.phase != "lobby":
        raise GameError("invalid_phase", "La partie a déjà démarré.")
    # Compte uniquement les joueurs (pas le présentateur)
    joueurs = [p for p in state.players if not p.is_presenter]
    if len(joueurs) < 2:
        raise GameError("invalid_payload", "Minimum 2 joueurs requis.")
    if len(state.themes) < 1:
        raise GameError("invalid_payload", "Minimum 1 thème requis.")
    rng = rng or random
    # Le premier joueur est tiré parmi les joueurs (pas le présentateur)
    # On trouve leur index réel dans state.players
    joueur_indices = [
        i for i, p in enumerate(state.players) if p.connected and not p.is_presenter
    ]
    if not joueur_indices:
        raise GameError("invalid_phase", "Aucun joueur connecté.")
    start_index = rng.choice(joueur_indices)
    return replace(
        state,
        phase="selection-pending",
        current_player_index=start_index,
        turn_status="ready",
        rotation_anchor_index=None,
        active_theme_index=None,
        tunnel_sub_phase=None,
        history=(),
    )


# --- Couche show : révélation des choix joueur ------------------------------


def reveal_choice(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    _require_playable_turn(state)
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
    _require_role(actor_role, "joueur")
    _require_playable_turn(state)
    if state.phase != "selection":
        raise GameError(
            "invalid_phase", "Le choix de thème n'est pas encore révélé."
        )
    _require_current_player(state, actor_role, actor_player_id)
    if type(index) is not int or not (0 <= index < len(state.themes)):
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
    _require_playable_turn(state)
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question-pending":
        raise GameError("invalid_phase", "Aucune question en attente de lancement du chrono.")
    return replace(state, tunnel_sub_phase="question")


# --- Jugement de la réponse orale (Présentateur) -----------------------------


def good_answer(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    _require_playable_turn(state)
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
        return _finish_turn(replace(
            state,
            themes=themes,
            players=players,
            history=history,
        ))

    return replace(state, themes=themes, tunnel_sub_phase="after-success-pending")


def bad_answer(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    _require_playable_turn(state)
    if state.phase != "tunnel" or state.tunnel_sub_phase != "question":
        raise GameError("invalid_phase", "Aucune question en cours à juger.")
    return _finish_turn(state)


def pass_question(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    _require_playable_turn(state)
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
        return _finish_turn(replace(
            state,
            themes=themes,
            players=players,
            history=history,
        ), rotate=False)

    return _finish_turn(replace(state, themes=themes), rotate=False)


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
    return _finish_turn(replace(
        state,
        themes=themes,
        players=players,
        history=history,
    ))


# --- Présence / absence d'un joueur (connexion WS individuelle) -------------
#
# Un joueur qui ferme son onglet ou perd sa connexion n'est PAS retiré de la
# partie : son tour actif est suspendu, les futurs tours sautent les absents.


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
    state = replace(state, players=players)
    if state.phase in ("lobby", "end"):
        return replace(
            state, turn_status="idle", current_player_index=None,
            rotation_anchor_index=None,
        )
    if state.turn_status == "waiting-eligible":
        anchor = state.rotation_anchor_index
        assert anchor is not None
        current = _next_player_index(players, anchor)
        if current is not None:
            return replace(
                state, current_player_index=current, turn_status="ready",
                rotation_anchor_index=None,
            )
    elif state.current_player_index == index:
        return replace(state, turn_status="ready" if connected else "active-absent")
    return state


# --- Fin de partie anticipée (Présentateur) ----------------------------------


def end_game_early(state: GameState, actor_role: Role) -> GameState:
    """Le Présentateur met fin à la partie en cours à tout moment et ramène
    tout le monde au lobby — joueurs et thèmes conservés (pour relancer
    rapidement), scores et progression remis à zéro, comme `reset_game` mais
    vers 'lobby' plutôt que de relancer directement une sélection."""
    _require_role(actor_role, "presentateur")
    return replace(
        state,
        # `connected` et `is_presenter` ne sont PAS réinitialisés ici.
        players=tuple(replace(p, points=0) for p in state.players),
        themes=tuple(reset_theme(t) for t in state.themes),
        current_player_index=None,
        turn_status="idle",
        rotation_anchor_index=None,
        active_theme_index=None,
        tunnel_sub_phase=None,
        history=(),
        phase="lobby",
    )


# --- Reset / quitter ---------------------------------------------------------


def reset_game(state: GameState, actor_role: Role) -> GameState:
    _require_role(actor_role, "presentateur")
    eligible = [
        i for i, p in enumerate(state.players) if p.connected and not p.is_presenter
    ]
    if state.phase == "lobby" or not state.themes or not eligible:
        raise GameError("invalid_phase", "Impossible de relancer la partie.")
    return replace(
        state,
        players=tuple(replace(p, points=0) for p in state.players),
        themes=tuple(reset_theme(t) for t in state.themes),
        current_player_index=eligible[0],
        turn_status="ready",
        rotation_anchor_index=None,
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
    "_ALLOWED_AVATARS",
    "_ALLOWED_AVATARS_SET",
    "pick_random_avatar",
    "add_player",
    "remove_player",
    "rename_player",
    "set_player_avatar",
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
