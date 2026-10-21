"""Private format v1. Public DTOs and runtime Room objects are never accepted."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.game.types import GameState, HistoryEntry, Player, Theme

FORMAT_VERSION = 1
Role = Literal["presentateur", "joueur", "ecran-principal"]
Nonnegative = Annotated[int, Field(ge=0)]
Square = Annotated[int, Field(ge=1, le=10)]
Progress = Annotated[int, Field(ge=0, le=10)]


class InvalidSnapshot(ValueError):
    def __init__(self):
        super().__init__("Invalid or unsupported private snapshot.")


class PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class SavedPlayer(PrivateModel):
    id: str
    name: Annotated[str, Field(min_length=1)]
    points: Nonnegative
    connected: bool
    avatar: str
    is_presenter: bool


class SavedTheme(PrivateModel):
    label: Annotated[str, Field(min_length=1)]
    progress_value: Progress
    validated_squares: Progress
    discovered: bool
    completed: bool
    nullified: tuple[Square, ...]

    @model_validator(mode="after")
    def consistent(self):
        if (self.validated_squares > self.progress_value
                or len(set(self.nullified)) != len(self.nullified)
                or any(n > self.progress_value for n in self.nullified)
                or self.completed != (self.validated_squares == 10)
                or self.completed != (self.progress_value == 10)):
            raise ValueError("Inconsistent theme")
        return self


class SavedHistory(PrivateModel):
    theme_label: str
    player_name: str
    points_gained: Nonnegative


class SavedGame(PrivateModel):
    phase: Literal["lobby", "selection-pending", "selection", "tunnel", "end"]
    players: tuple[SavedPlayer, ...]
    themes: tuple[SavedTheme, ...]
    current_player_index: Nonnegative | None
    active_theme_index: Nonnegative | None
    tunnel_sub_phase: Literal["question-pending", "question", "after-success-pending", "after-success-open"] | None
    history: tuple[SavedHistory, ...]
    turn_status: Literal["idle", "ready", "active-absent", "waiting-eligible"]
    rotation_anchor_index: Nonnegative | None

    @classmethod
    def from_game(cls, state: GameState) -> SavedGame:
        return cls(
            phase=state.phase,
            players=tuple(SavedPlayer(id=p.id, name=p.name, points=p.points,
                                     connected=p.connected, avatar=p.avatar,
                                     is_presenter=p.is_presenter) for p in state.players),
            themes=tuple(SavedTheme(label=t.label, progress_value=t.progress_value,
                                    validated_squares=t.validated_squares,
                                    discovered=t.discovered, completed=t.completed,
                                    nullified=t.nullified) for t in state.themes),
            history=tuple(SavedHistory(theme_label=h.theme_label, player_name=h.player_name,
                                       points_gained=h.points_gained) for h in state.history),
            current_player_index=state.current_player_index, active_theme_index=state.active_theme_index,
            tunnel_sub_phase=state.tunnel_sub_phase, turn_status=state.turn_status,
            rotation_anchor_index=state.rotation_anchor_index,
        )

    def to_game(self) -> GameState:
        return GameState(
            phase=self.phase, players=tuple(Player(**p.model_dump()) for p in self.players),
            themes=tuple(Theme(**t.model_dump()) for t in self.themes),
            history=tuple(HistoryEntry(**h.model_dump()) for h in self.history),
            current_player_index=self.current_player_index, active_theme_index=self.active_theme_index,
            tunnel_sub_phase=self.tunnel_sub_phase, turn_status=self.turn_status,
            rotation_anchor_index=self.rotation_anchor_index,
        )

    @model_validator(mode="after")
    def consistent(self):
        from app.game.engine import _ALLOWED_AVATARS_SET

        ids = [p.id for p in self.players]
        avatars = [p.avatar for p in self.players]
        if (len(ids) != len(set(ids)) or len(avatars) != len(set(avatars))
                or any(a not in _ALLOWED_AVATARS_SET for a in avatars)
                or len(ids) > 16):
            raise ValueError("Invalid players/themes")
        for i in (self.current_player_index, self.rotation_anchor_index):
            if i is not None and (i >= len(ids) or self.players[i].is_presenter):
                raise ValueError("Invalid actor reference")
        if self.active_theme_index is not None and self.active_theme_index >= len(self.themes):
            raise ValueError("Invalid theme reference")
        if self.phase in ("lobby", "end"):
            if (self.turn_status != "idle" or self.current_player_index is not None
                    or self.rotation_anchor_index is not None):
                raise ValueError("Invalid idle turn")
        elif self.turn_status == "waiting-eligible":
            if (self.phase != "selection-pending" or self.current_player_index is not None
                    or self.rotation_anchor_index is None
                    or any(p.connected and not p.is_presenter for p in self.players)):
                raise ValueError("Invalid waiting turn")
        elif self.turn_status in ("ready", "active-absent"):
            if (self.current_player_index is None or self.rotation_anchor_index is not None
                    or self.players[self.current_player_index].connected != (self.turn_status == "ready")):
                raise ValueError("Invalid active turn")
        else:
            raise ValueError("Invalid turn status")
        if (self.phase == "tunnel") != (self.tunnel_sub_phase is not None):
            raise ValueError("Invalid tunnel subphase")
        if (self.phase == "tunnel") != (self.active_theme_index is not None):
            raise ValueError("Invalid active theme")
        if self.active_theme_index is not None and self.themes[self.active_theme_index].completed:
            raise ValueError("Completed active theme")
        return self


class SavedSession(PrivateModel):
    participant_id: UUID
    name: Annotated[str, Field(min_length=1)]
    role: Role
    proof_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", repr=False)]
    status: Literal["active", "revoked"]
    created_at: datetime
    revoked_at: datetime | None

    @model_validator(mode="after")
    def consistent(self):
        if ((self.status == "revoked") != (self.revoked_at is not None)
                or self.created_at.utcoffset() != timezone.utc.utcoffset(None)
                or (self.revoked_at is not None and (
                    self.revoked_at.utcoffset() != timezone.utc.utcoffset(None)
                    or self.revoked_at < self.created_at))):
            raise ValueError("Invalid session lifecycle")
        return self


class Snapshot(PrivateModel):
    format_version: Literal[1]
    room_id: UUID
    game_id: UUID
    write_id: UUID
    code: Annotated[str, Field(pattern=r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}$")]
    revision: Annotated[int, Field(ge=1)]
    status: Literal["live", "closed", "expired"]
    created_at: datetime
    closed_at: datetime | None
    idle_deadline_utc: datetime
    last_liveness_at: datetime
    presenter_id: UUID
    state: SavedGame
    sessions: tuple[SavedSession, ...]

    @model_validator(mode="after")
    def consistent(self):
        dates = (self.created_at, self.idle_deadline_utc, self.last_liveness_at, self.closed_at)
        if any(d is not None and d.utcoffset() != timezone.utc.utcoffset(None) for d in dates):
            raise ValueError("UTC required")
        if ((self.status == "live") != (self.closed_at is None)
                or self.last_liveness_at < self.created_at
                or self.idle_deadline_utc <= self.last_liveness_at
                or (self.closed_at is not None and self.closed_at < self.created_at)):
            raise ValueError("Invalid room lifecycle")
        sessions = {str(s.participant_id): s for s in self.sessions}
        if len(sessions) != len(self.sessions):
            raise ValueError("Duplicate participant")
        current = {pid: s for pid, s in sessions.items() if s.status == "active"}
        if self.status != "live" and current:
            raise ValueError("Closed sessions must be revoked")
        players = {p.id: p for p in self.state.players}
        for pid, player in players.items():
            if (str(UUID(pid)) != pid or pid not in sessions
                    or sessions[pid].role == "ecran-principal"
                    or sessions[pid].name != player.name
                    or player.is_presenter != (pid == str(self.presenter_id))
                    or player.is_presenter != (sessions[pid].role == "presentateur")
                    or (self.status == "live" and pid not in current)):
                raise ValueError("Inconsistent player session")
        if (str(self.presenter_id) not in players
                or sum(p.is_presenter for p in players.values()) != 1
                or any(s.role != "ecran-principal" and pid not in players for pid, s in current.items())):
            raise ValueError("Invalid membership")
        return self


def encode(snapshot: Snapshot) -> str:
    if type(snapshot) is not Snapshot:
        raise InvalidSnapshot()
    # Revalidate even model_copy/model_construct objects at the storage boundary.
    payload = snapshot.model_dump_json()
    decode(payload)
    return payload


def decode(payload: str) -> Snapshot:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidSnapshot()
            result[key] = value
        return result

    try:
        parsed = json.loads(payload, object_pairs_hook=unique)
        # Literal[1] accepts True in some validators; the envelope is exact.
        if (not isinstance(parsed, dict) or type(parsed.get("format_version")) is not int
                or parsed["format_version"] != FORMAT_VERSION):
            raise InvalidSnapshot()
        return Snapshot.model_validate_json(payload)
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise InvalidSnapshot() from None
