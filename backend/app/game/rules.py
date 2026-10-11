"""Règles de jeu pures — miroir exact de frontend/src/game/rules.ts.

Ces fonctions sont strictement sans effet de bord et ne connaissent rien du
transport (WebSocket/REST) ni des rôles — c'est la couche réutilisée à
l'identique par le mode room multi (Bloc 5) et le futur mode room solo
(Bloc 7bis). Voir la spécification figée dans
docs/exec-plans/reconstruction-le-grand-tunneg.md pour la justification de
chaque règle.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import SquareColor, Theme


def points_for_square(k: int) -> int:
    """Barème de points par case (k 1-indexé)."""
    if 1 <= k <= 3:
        return 1
    if 4 <= k <= 6:
        return 2
    if 7 <= k <= 9:
        return 3
    if k == 10:
        return 5
    return 0


def square_color(theme: Theme, k: int) -> SquareColor:
    """Couleur d'une case k pour un thème donné (ordre de priorité strict)."""
    if k in theme.nullified:
        return "black"
    if k <= theme.validated_squares:
        return "gray"
    if k <= theme.progress_value:
        return "green"
    if k - 1 == theme.progress_value and theme.discovered:
        return "yellow"
    return "empty"


def create_theme(label: str) -> Theme:
    return Theme(label=label)


def reset_theme(theme: Theme) -> Theme:
    return create_theme(theme.label)


@dataclass(frozen=True)
class CoffrageResult:
    theme: Theme
    points_gained: int


def coffrer(theme: Theme) -> CoffrageResult:
    """Crédite les points de toutes les cases entre validated_squares+1 et
    progress_value (incluses), sauf celles nullifiées, puis marque ces cases
    comme validées. Retourne le thème mis à jour et le total de points gagnés.
    """
    points_gained = 0
    validated_squares = theme.validated_squares
    for i in range(theme.validated_squares + 1, theme.progress_value + 1):
        validated_squares = i
        if i not in theme.nullified:
            points_gained += points_for_square(i)
    return CoffrageResult(
        theme=Theme(
            label=theme.label,
            progress_value=theme.progress_value,
            validated_squares=validated_squares,
            discovered=theme.discovered,
            completed=theme.completed,
            nullified=theme.nullified,
        ),
        points_gained=points_gained,
    )


@dataclass(frozen=True)
class PoursuivreResult:
    theme: Theme
    auto_coffrage: bool
    points_gained: int


def poursuivre(theme: Theme) -> PoursuivreResult:
    """Avance la progression suite à une bonne réponse ou un passage."""
    if theme.progress_value == 9:
        advanced = Theme(
            label=theme.label,
            progress_value=10,
            validated_squares=theme.validated_squares,
            discovered=theme.discovered,
            completed=theme.completed,
            nullified=theme.nullified,
        )
        result = coffrer(advanced)
        completed_theme = Theme(
            label=result.theme.label,
            progress_value=result.theme.progress_value,
            validated_squares=result.theme.validated_squares,
            discovered=result.theme.discovered,
            completed=True,
            nullified=result.theme.nullified,
        )
        return PoursuivreResult(
            theme=completed_theme,
            auto_coffrage=True,
            points_gained=result.points_gained,
        )
    return PoursuivreResult(
        theme=Theme(
            label=theme.label,
            progress_value=theme.progress_value + 1,
            validated_squares=theme.validated_squares,
            discovered=theme.discovered,
            completed=theme.completed,
            nullified=theme.nullified,
        ),
        auto_coffrage=False,
        points_gained=0,
    )


__all__ = [
    "points_for_square",
    "square_color",
    "create_theme",
    "reset_theme",
    "coffrer",
    "poursuivre",
    "CoffrageResult",
    "PoursuivreResult",
]
