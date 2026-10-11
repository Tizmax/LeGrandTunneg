"""Types du moteur de règles de jeu — miroir exact de frontend/src/game/types.ts.

Toutes les structures sont des dataclasses *frozen* (immuables) pour refléter
le style "spread immutable" du reducer TypeScript d'origine : chaque
transition de règle retourne un nouvel objet plutôt que de muter en place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

SquareColor = Literal["black", "gray", "green", "yellow", "empty"]

GamePhase = Literal[
    "lobby",  # attente des joueurs + saisie des thèmes (écran unique, fusion 2026-10-11)
    "selection-pending",  # choice_pending : choix de thème éligible, pas encore révélé
    "selection",  # choice_open : grille de sélection révélée, cliquable
    "tunnel",  # tunnel de jeu en cours pour un thème
    "end",  # podium de fin de partie
]

TunnelSubPhase = Literal[
    "question-pending",  # le Présentateur pose sa question à l'oral, chrono pas encore lancé
    "question",  # chrono lancé, question en cours, en attente du jugement du Présentateur
    "after-success-pending",  # choice_pending : Continuer/Coffrer éligible, pas révélé
    "after-success-open",  # choice_open : Continuer/Coffrer révélés, cliquables
]


@dataclass(frozen=True)
class Theme:
    label: str
    progress_value: int = 0  # 0..10
    validated_squares: int = 0  # 0..10
    discovered: bool = False
    completed: bool = False
    nullified: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Player:
    # id = local_player_id d'origine (UUID) — absent du POC frontend-only,
    # nécessaire côté serveur pour vérifier "c'est bien ce joueur qui parle".
    id: str
    name: str
    points: int = 0


@dataclass(frozen=True)
class HistoryEntry:
    theme_label: str
    player_name: str
    points_gained: int


@dataclass(frozen=True)
class GameState:
    phase: GamePhase = "lobby"
    players: tuple[Player, ...] = field(default_factory=tuple)
    themes: tuple[Theme, ...] = field(default_factory=tuple)
    current_player_index: int = 0
    active_theme_index: int | None = None
    tunnel_sub_phase: TunnelSubPhase | None = None
    history: tuple[HistoryEntry, ...] = field(default_factory=tuple)


def initial_state() -> GameState:
    return GameState()


__all__ = [
    "SquareColor",
    "GamePhase",
    "TunnelSubPhase",
    "Theme",
    "Player",
    "HistoryEntry",
    "GameState",
    "initial_state",
    "replace",
]
