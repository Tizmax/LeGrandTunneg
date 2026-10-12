"""Endpoints REST de gestion de room (création, jointure) — Bloc 4/5.

Portée de cette passe : uniquement la partie room multi en mémoire. Pas de
banque de thèmes prédéfinis, pas d'historique/stats (hors scope ici, voir
docs/exec-plans/reconstruction-le-grand-tunneg.md Bloc 4 scope complet pour
une passe ultérieure).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.game import engine
from app.game.serialize import serialize_state
from app.rooms.manager import RoomNotFoundError, room_manager

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    pseudo: str = Field(min_length=1, max_length=24)


class CreateRoomResponse(BaseModel):
    code: str
    localPlayerId: str
    role: Literal["presentateur"]


@router.post("", response_model=CreateRoomResponse)
def create_room(body: CreateRoomRequest) -> CreateRoomResponse:
    try:
        room, local_player_id = room_manager.create_room(body.pseudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreateRoomResponse(
        code=room.code, localPlayerId=local_player_id, role="presentateur"
    )


class JoinRoomRequest(BaseModel):
    pseudo: str = Field(min_length=1, max_length=24)
    role: Literal["joueur", "ecran-principal"] = "joueur"
    # Fourni par le client lors d'une reconnexion : s'il correspond à un
    # participant déjà connu de la room, c'est traité comme une reconnexion
    # (voir docs/websocket-protocol.md, section "Créer/Rejoindre une room").
    localPlayerId: str | None = None


class JoinRoomResponse(BaseModel):
    code: str
    localPlayerId: str
    role: Literal["presentateur", "joueur", "ecran-principal"]
    state: dict


@router.post("/{code}/join", response_model=JoinRoomResponse)
async def join_room(code: str, body: JoinRoomRequest) -> JoinRoomResponse:
    code = code.upper()
    try:
        room, local_player_id, role = room_manager.join_room(
            code, body.pseudo, body.role, body.localPlayerId
        )
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Room introuvable.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except engine.GameError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc

    # Notifie immédiatement les connexions WS déjà ouvertes (ex: le
    # Présentateur dans le lobby) qu'un nouveau participant vient de
    # rejoindre — sans ça, l'état ne se synchronise qu'au prochain message WS
    # émis par quelqu'un d'autre (bug détecté lors du playtest Bloc 7).
    await room_manager.broadcast_state(code)

    return JoinRoomResponse(
        code=room.code,
        localPlayerId=local_player_id,
        role=role,
        state=serialize_state(room.state),
    )


__all__ = ["router"]
