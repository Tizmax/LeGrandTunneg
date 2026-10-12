"""Sérialisation GameState (Python, snake_case) -> DTO JSON camelCase,
conforme au schéma documenté dans docs/websocket-protocol.md.

Le Présentateur apparaît désormais dans `players[]` avec `isPresenter: true`
(unification 2026-10-12). Les champs `presentateurName`/`presentateurAvatar`
ont été retirés du payload.
"""

from __future__ import annotations

from typing import Any

from .types import GameState


def serialize_state(state: GameState) -> dict[str, Any]:
    return {
        "phase": state.phase,
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "points": p.points,
                "connected": p.connected,
                "avatar": p.avatar,
                "isPresenter": p.is_presenter,
            }
            for p in state.players
        ],
        "themes": [
            {
                "label": t.label,
                "progressValue": t.progress_value,
                "validatedSquares": t.validated_squares,
                "discovered": t.discovered,
                "completed": t.completed,
                "nullified": list(t.nullified),
            }
            for t in state.themes
        ],
        "currentPlayerIndex": state.current_player_index,
        "activeThemeIndex": state.active_theme_index,
        "tunnelSubPhase": state.tunnel_sub_phase,
        "history": [
            {
                "themeLabel": h.theme_label,
                "playerName": h.player_name,
                "pointsGained": h.points_gained,
            }
            for h in state.history
        ],
    }


__all__ = ["serialize_state"]
