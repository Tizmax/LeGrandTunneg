"""Authenticated, bounded WebSocket protocol with live socket authority."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.api.rooms import valid_proof
from app.core.limits import TokenBucket
from app.core.settings import settings
from app.game import engine
from app.rooms.manager import CapacityError, RoomNotFoundError, UnknownParticipantError, room_manager
from app.persistence.store import PersistenceUnavailable

router = APIRouter()
upgrade_bucket = TokenBucket(settings.ws_upgrade_rate_per_second, settings.ws_upgrade_rate_burst)
global_bucket = TokenBucket(settings.ws_global_rate_per_second, settings.ws_global_rate_burst)

_EMPTY = {
    "game:start": engine.start_game, "choice:reveal": engine.reveal_choice,
    "timer:start": engine.start_timer, "answer:good": engine.good_answer,
    "answer:bad": engine.bad_answer, "answer:pass": engine.pass_question,
    "game:reset": engine.reset_game, "game:end_early": engine.end_game_early,
}
_FIELDS = {"theme:add": "label", "theme:remove": "index", "theme:select": "index",
           "player:remove": "index", "player:rename": "name", "player:set_avatar": "avatar",
           "presenter:transfer": "targetPlayerId"}
_OTHERS = {"room:quit", "answer:continue", "answer:vault"}


def invalid() -> None:
    raise engine.GameError("invalid_payload", "Invalid message.")


async def receive(socket: WebSocket) -> dict:
    frame = await socket.receive()
    if frame["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(frame.get("code", 1000))
    text = frame.get("text")
    try:
        raw = text.encode("utf-8") if text is not None else frame.get("bytes", b"")
    except UnicodeError:
        invalid()
    if len(raw) > settings.max_message_bytes:
        raise OverflowError
    if text is None:
        invalid()
    try:
        message = json.loads(text)
    except (ValueError, UnicodeError, RecursionError):
        invalid()
    if (not isinstance(message, dict) or set(message) != {"type", "payload"}
            or not isinstance(message["type"], str) or not isinstance(message["payload"], dict)):
        invalid()
    return message


def validate(message: dict, room) -> tuple[str, dict]:
    event, payload = message["type"], message["payload"]
    if event in _EMPTY or event in _OTHERS:
        if payload:
            invalid()
    elif event in _FIELDS:
        key = _FIELDS[event]
        if set(payload) != {key}:
            invalid()
        value = payload[key]
        if key == "index":
            count = len(room.state.players) if event == "player:remove" else len(room.state.themes)
            if type(value) is not int or not 0 <= value < count:
                invalid()
        elif key in ("label", "name"):
            maximum = settings.max_name_chars if key == "name" else settings.max_theme_label_chars
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                invalid()
            try:
                value.encode("utf-8")
            except UnicodeError:
                invalid()
            payload = {key: value.strip()}
        elif key == "avatar":
            if not isinstance(value, str) or value not in engine._ALLOWED_AVATARS_SET:
                invalid()
        elif not valid_proof({"localPlayerId": value, "sessionToken": "A" * 43}):
            invalid()
    else:
        invalid()
    return event, payload


async def deny(socket: WebSocket, status: int) -> None:
    if "websocket.http.response" in socket.scope.get("extensions", {}):
        await socket.send_denial_response(JSONResponse({"detail": {"code": "rate_limited" if status == 429 else "forbidden_origin",
                                                                   "message": "Connection refused."}}, status_code=status))
    else:
        await socket.close(code=1008)


@router.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str) -> None:
    origins = websocket.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in settings.allowed_origins or websocket.query_params:
        await deny(websocket, 403)
        return
    if (not upgrade_bucket.consume()
            or room_manager.preauth_connections >= settings.max_preauth_connections
            or len(room_manager.authenticated_connections) + len(room_manager.auth_reservations)
            >= settings.max_authenticated_connections):
        await deny(websocket, 429)
        return
    room_manager.preauth_connections += 1
    reserved = True
    room, pid = None, None
    reader = None
    messages = asyncio.Queue(maxsize=settings.ws_command_rate_burst)
    transport_ended = asyncio.Event()
    transport_close = None
    transport_disconnected = False

    async def read_transport():
        nonlocal transport_close, transport_disconnected
        try:
            while True:
                try:
                    message = await receive(websocket)
                except engine.GameError:
                    message = None
                try:
                    messages.put_nowait(message)
                except asyncio.QueueFull:
                    # No unbounded command backlog while the processor awaits DB.
                    transport_close = (4429, "rate_limited")
                    return
        except OverflowError:
            transport_close = (1009, "")
        except WebSocketDisconnect:
            transport_disconnected = True
        except (RuntimeError, OSError):
            pass
        finally:
            room_manager.lost_transports.add(websocket)
            room_manager.lose_connection(room, pid, websocket)
            transport_ended.set()

    try:
        await websocket.accept()
        try:
            async with asyncio.timeout(settings.auth_timeout_seconds):
                auth = await receive(websocket)
                if auth["type"] != "session:auth" or set(auth["payload"]) != {"localPlayerId", "sessionToken"} or not valid_proof(auth["payload"]):
                    invalid()
                pid = auth["payload"]["localPlayerId"]
                room = room_manager.get_room(code)
                room_manager.reserve_auth(websocket)
                reader = asyncio.create_task(read_transport())
                async with room.lock:
                    previous = await room_manager.attach_locked(room, pid, auth["payload"]["sessionToken"], websocket)
                del auth
        except TimeoutError:
            if not transport_ended.is_set():
                await room_manager.close_socket(websocket, 4408, "auth_timeout")
            return
        except engine.GameError:
            await room_manager.close_socket(websocket, 1008, "invalid_payload")
            return
        except RoomNotFoundError:
            await room_manager.terminal(None, websocket, "room_closed")
            return
        except UnknownParticipantError:
            await room_manager.terminal(None, websocket, "session_revoked")
            return
        except CapacityError:
            await room_manager.close_socket(websocket, 4429, "rate_limited")
            return
        except PersistenceUnavailable:
            if transport_ended.is_set():
                return
            await asyncio.wait_for(websocket.send_json({"type": "error", "payload": {
                "code": PersistenceUnavailable.code, "message": PersistenceUnavailable.message,
            }}), settings.send_timeout_seconds)
            await room_manager.close_socket(websocket, 1013, "persistence_unavailable")
            return
        room_manager.preauth_connections -= 1
        reserved = False
        if previous:
            await room_manager.terminal(room, previous, "session_replaced")
        delivery = room.deliveries[websocket]
        await asyncio.wait_for(delivery.acknowledged.wait(), settings.send_timeout_seconds)
        bucket = TokenBucket(settings.ws_command_rate_per_second, settings.ws_command_rate_burst)
        while True:
            receiving = asyncio.create_task(messages.get())
            ending = asyncio.create_task(delivery.ended.wait())
            disconnected = asyncio.create_task(transport_ended.wait())
            try:
                done, _ = await asyncio.wait((receiving, ending, disconnected), return_when=asyncio.FIRST_COMPLETED)
                if ending in done or disconnected in done:
                    return
                message = receiving.result()
            except engine.GameError:
                message = None
            finally:
                receiving.cancel()
                ending.cancel()
                disconnected.cancel()
                await asyncio.gather(receiving, ending, disconnected, return_exceptions=True)
            terminals = []
            error = None
            async with room.lock:
                # A superseded socket cannot issue commands or change presence.
                if room.closed or room.connections.get(pid) is not websocket or pid not in room.proofs:
                    return
                if not bucket.consume() or not global_bucket.consume():
                    room_manager.invalidate_locked(room, websocket, "rate_limited")
                    return
                try:
                    await room_manager.ensure_live(room)
                    if message is None:
                        invalid()
                    event, payload = validate(message, room)
                    role = room.roles[pid]
                    if role == "ecran-principal":
                        raise engine.GameError("forbidden_role", "Screens cannot issue game commands.")
                    candidate = room_manager.candidate(room)
                    if event == "room:quit":
                        engine.quit_to_menu(room.state, role)
                        terminals = [(s, "room_closed") for s in await room_manager.close_room_locked(room)]
                    elif event == "player:remove":
                        target = room.state.players[payload["index"]].id
                        candidate.state = engine.remove_player(room.state, payload["index"], role)
                        candidate.proofs.pop(target, None)
                        candidate.roles.pop(target, None)
                        candidate.names.pop(target, None)
                    elif event == "presenter:transfer":
                        target = payload["targetPlayerId"]
                        candidate.state = engine.transfer_presenter(room.state, target, role)
                        candidate.roles[room.presentateur_id] = "joueur"
                        candidate.roles[target] = "presentateur"
                        candidate.presentateur_id = target
                    elif event == "player:rename":
                        candidate.state = engine.rename_player(room.state, role, pid, payload["name"])
                        candidate.names[pid] = payload["name"]
                    elif event == "player:set_avatar":
                        candidate.state = engine.set_player_avatar(room.state, pid, payload["avatar"])
                    elif event == "theme:add":
                        candidate.state = engine.add_theme(room.state, payload["label"], role)
                    elif event == "theme:remove":
                        candidate.state = engine.remove_theme(room.state, payload["index"], role)
                    elif event == "theme:select":
                        candidate.state = engine.select_theme(room.state, payload["index"], role, pid)
                    elif event in ("answer:continue", "answer:vault"):
                        handler = engine.continue_tunnel if event == "answer:continue" else engine.vault
                        candidate.state = handler(room.state, role, pid)
                    else:
                        candidate.state = _EMPTY[event](room.state, role)
                    if not room.closed:
                        await room_manager.commit_locked(room, candidate, event, pid, liveness=True)
                        if event == "player:remove":
                            target_socket = room.connections.pop(target, None)
                            if target_socket:
                                room_manager.invalidate_locked(room, target_socket, "player_kicked")
                                terminals = [(target_socket, "player_kicked")]
                        room_manager.publish_locked(room)
                except engine.GameError as exc:
                    error = {"type": "error", "payload": {"code": exc.code, "message": exc.message}}
                except PersistenceUnavailable:
                    error = {"type": "error", "payload": {
                        "code": PersistenceUnavailable.code, "message": PersistenceUnavailable.message,
                    }}
                except RoomNotFoundError:
                    return
            if error and not transport_ended.is_set():
                await room_manager.send(room, websocket, error)
            if terminals:
                await asyncio.gather(*(room_manager.terminal(room, s, reason) for s, reason in terminals))
            if room.closed:
                return
    except OverflowError:
        await room_manager.close_socket(websocket, 1009)
    except (WebSocketDisconnect, RuntimeError, TimeoutError, OSError):
        pass
    finally:
        room_manager.auth_reservations.discard(websocket)
        if reader:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if reserved:
            room_manager.preauth_connections -= 1
        if room is not None and pid is not None:
            cleanup = asyncio.create_task(room_manager.release(
                room, pid, websocket, transport_close=transport_close,
                transport_disconnected=transport_disconnected))
            await asyncio.shield(cleanup)
