"""Strict room membership and proof-only resumption endpoints."""

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.limits import TokenBucket
from app.core.settings import settings
from app.game import engine
from app.game.serialize import serialize_state
from app.rooms.manager import CapacityError, RoomNotFoundError, UnknownParticipantError, room_manager
from app.persistence.store import PersistenceUnavailable

rest_bucket = TokenBucket(settings.rest_rate_per_second, settings.rest_rate_burst)
body_readers = 0
operations = 0


async def admission():
    global operations
    if operations >= settings.max_rest_operations:
        fail(503, "capacity_exceeded", "Request capacity exceeded.")
    operations += 1
    try:
        async with asyncio.timeout(settings.rest_operation_timeout_seconds):
            yield
    except TimeoutError:
        fail(503, PersistenceUnavailable.code, PersistenceUnavailable.message)
    finally:
        operations -= 1


router = APIRouter(prefix="/api/rooms", tags=["rooms"], dependencies=[Depends(admission)])


def valid_proof(payload: dict) -> bool:
    pid, token = payload.get("localPlayerId"), payload.get("sessionToken")
    if not isinstance(pid, str) or not isinstance(token, str):
        return False
    try:
        canonical = str(uuid.UUID(pid)) == pid
    except ValueError:
        return False
    # The final character must encode the two remaining bits canonically.
    return canonical and re.fullmatch(r"[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]", token) is not None


def fail(status: int, code: str, message: str, headers: dict | None = None) -> None:
    raise HTTPException(status_code=status, detail={"code": code, "message": message},
                        headers={"Cache-Control": "no-store", **(headers or {})})


def name(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= settings.max_name_chars:
        fail(422, "invalid_payload", "Invalid payload.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        fail(422, "invalid_payload", "Invalid payload.")
    return value.strip()


async def body(request: Request) -> dict:
    global body_readers
    if not rest_bucket.consume():
        fail(429, "rate_limited", "Rate limited.", {"Retry-After": str(rest_bucket.retry_after())})
    # Admission is atomic on the single event loop and never queues a reader.
    if body_readers >= settings.max_rest_body_readers:
        fail(503, "capacity_exceeded", "Body reader capacity exceeded.")
    body_readers += 1
    try:
        data = bytearray()
        try:
            # One absolute deadline for the whole stream, not per chunk.
            async with asyncio.timeout(settings.rest_body_timeout_seconds):
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > settings.max_rest_body_bytes:
                        fail(413, "payload_too_large", "Payload too large.")
        except TimeoutError:
            fail(408, "request_timeout", "Request body timed out.")
        try:
            value = json.loads(data)
        except (ValueError, UnicodeDecodeError, RecursionError):
            fail(422, "invalid_payload", "Invalid payload.")
        if not isinstance(value, dict):
            fail(422, "invalid_payload", "Invalid payload.")
        return value
    finally:
        body_readers -= 1


@router.post("")
async def create_room(request: Request) -> JSONResponse:
    payload = await body(request)
    if set(payload) != {"pseudo"}:
        fail(422, "invalid_payload", "Invalid payload.")
    pseudo = name(payload["pseudo"])
    try:
        room, pid, token = await room_manager.create_room(pseudo)
    except PersistenceUnavailable:
        fail(503, PersistenceUnavailable.code, PersistenceUnavailable.message)
    except CapacityError:
        fail(503, "capacity_exceeded", "Room capacity exceeded.")
    return JSONResponse({"code": room.code, "localPlayerId": pid, "role": "presentateur",
                         "sessionToken": token}, headers={"Cache-Control": "no-store"})


@router.post("/{code}/join")
async def join_room(code: str, request: Request) -> JSONResponse:
    payload = await body(request)
    resume = set(payload) == {"localPlayerId", "sessionToken"}
    if resume:
        if not valid_proof(payload):
            fail(422, "invalid_payload", "Invalid payload.")
    elif set(payload) not in ({"pseudo"}, {"pseudo", "role"}):
        fail(422, "invalid_payload", "Invalid payload.")
    else:
        payload["pseudo"] = name(payload["pseudo"])
        if payload.get("role", "joueur") not in ("joueur", "ecran-principal"):
            fail(422, "invalid_payload", "Invalid payload.")
    try:
        room = room_manager.get_room(code)
        async with room.lock:
            await room_manager.ensure_live(room)
            if resume:
                pid = payload["localPlayerId"]
                room_manager.verify(room, pid, payload["sessionToken"])
                token = None
            else:
                pid, token = await room_manager.join_room_locked(room, payload["pseudo"], payload.get("role", "joueur"))
                room_manager.publish_locked(room)
            unavailable = bool(room.absent or room.blocked)
            if unavailable and resume:
                raise PersistenceUnavailable()
            result = {"code": room.code, "localPlayerId": pid, "role": room.roles[pid],
                      "state": None if unavailable else serialize_state(room.state)}
            if unavailable:
                result["persistenceUnavailable"] = True
            if token:
                result["sessionToken"] = token
    except RoomNotFoundError:
        fail(404, "room_not_found", "Room not found.")
    except PersistenceUnavailable:
        fail(503, PersistenceUnavailable.code, PersistenceUnavailable.message)
    except UnknownParticipantError:
        fail(401, "session_revoked", "Session unavailable.")
    except CapacityError:
        fail(409, "capacity_exceeded", "Membership capacity exceeded.")
    except engine.GameError as exc:
        fail(409, exc.code, exc.message)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
