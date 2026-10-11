"""Handler WebSocket /ws/{code} — Bloc 5 (scope mémoire, sans persistance).

Implémente le protocole documenté dans docs/websocket-protocol.md : enveloppe
`{type, payload}`, dispatch vers `app.game.engine`, broadcast `room:state_sync`
à toute la room après chaque action acceptée, `error` ciblé au seul client
fautif en cas de rejet (rôle incorrect, mauvais tour, phase invalide, payload
invalide) sans aucune mutation d'état ni broadcast dans ce cas.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.game import engine
from app.game.serialize import serialize_state
from app.game.types import GameState
from app.rooms.manager import RoomNotFoundError, UnknownParticipantError, room_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "payload": {"code": code, "message": message}})


async def _send_state_sync(
    websocket: WebSocket, code: str, role: str, local_player_id: str, state: GameState
) -> None:
    await websocket.send_json(
        {
            "type": "room:state_sync",
            "payload": {
                "code": code,
                "role": role,
                "localPlayerId": local_player_id,
                "state": serialize_state(state),
            },
        }
    )


async def _broadcast_state(code: str) -> None:
    # Délégué à RoomManager.broadcast_state, partagé avec la route REST
    # POST /api/rooms/{code}/join qui doit aussi notifier les connexions WS
    # déjà actives (voir app/rooms/manager.py).
    await room_manager.broadcast_state(code)


async def _broadcast_closed(code: str) -> None:
    room = room_manager.get_room(code)
    for conn in list(room.connections.values()):
        try:
            await conn.send_json({"type": "room:closed", "payload": {}})
            await conn.close()
        except Exception:
            pass


# --- Dispatch table : type de message -> fonction moteur -------------------
#
# Chaque handler reçoit (state, payload, role, local_player_id) et renvoie le
# nouvel état, ou lève engine.GameError. Les actions Présentateur ignorent
# local_player_id ; les actions "joueur concerné" l'utilisent pour vérifier
# players[current_player_index].id == local_player_id (fait par engine.py).


def _h_theme_add(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.add_theme(state, payload.get("label", ""), role)


def _h_theme_remove(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.remove_theme(state, _require_int(payload, "index"), role)


def _h_player_remove(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.remove_player(state, _require_int(payload, "index"), role)


def _h_go_to_themes(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.go_to_themes(state, role)


def _h_game_start(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.start_game(state, role)


def _h_choice_reveal(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.reveal_choice(state, role)


def _h_theme_select(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.select_theme(state, _require_int(payload, "index"), role, pid)


def _h_answer_good(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.good_answer(state, role)


def _h_answer_bad(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.bad_answer(state, role)


def _h_answer_pass(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.pass_question(state, role)


def _h_answer_continue(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.continue_tunnel(state, role, pid)


def _h_answer_vault(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.vault(state, role, pid)


def _h_game_reset(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.reset_game(state, role)


def _require_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise engine.GameError("invalid_payload", f"Champ '{key}' manquant ou invalide.")
    return value


_HANDLERS: dict[str, Callable[[GameState, dict, str, str], GameState]] = {
    "theme:add": _h_theme_add,
    "theme:remove": _h_theme_remove,
    "player:remove": _h_player_remove,
    "lobby:go_to_themes": _h_go_to_themes,
    "game:start": _h_game_start,
    "choice:reveal": _h_choice_reveal,
    "theme:select": _h_theme_select,
    "answer:good": _h_answer_good,
    "answer:bad": _h_answer_bad,
    "answer:pass": _h_answer_pass,
    "answer:continue": _h_answer_continue,
    "answer:vault": _h_answer_vault,
    "game:reset": _h_game_reset,
    # "room:quit" est traité à part : il ferme la room plutôt que de
    # simplement muter l'état (voir boucle principale ci-dessous).
}


@router.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str, local_player_id: str) -> None:
    code = code.upper()
    try:
        room = room_manager.attach_connection(code, local_player_id, websocket)
    except RoomNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="room_not_found")
        return
    except UnknownParticipantError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="unknown_participant")
        return

    await websocket.accept()
    role = room.roles[local_player_id]
    await _send_state_sync(websocket, code, role, local_player_id, room.state)

    try:
        while True:
            message: dict[str, Any] = await websocket.receive_json()
            msg_type = message.get("type")
            payload = message.get("payload") or {}

            if msg_type == "room:quit":
                async with room.lock:
                    try:
                        engine.quit_to_menu(room.state, role)
                    except engine.GameError as exc:
                        await _send_error(websocket, exc.code, exc.message)
                        continue
                    await _broadcast_closed(code)
                    room_manager.close_room(code)
                return

            handler = _HANDLERS.get(msg_type)
            if handler is None:
                await _send_error(
                    websocket, "invalid_payload", f"Type de message inconnu: {msg_type!r}"
                )
                continue

            async with room.lock:
                try:
                    new_state = handler(room.state, payload, role, local_player_id)
                except engine.GameError as exc:
                    await _send_error(websocket, exc.code, exc.message)
                    continue
                room.state = new_state
                await _broadcast_state(code)

    except WebSocketDisconnect:
        room_manager.detach_connection(code, local_player_id)
    except Exception:
        logger.exception("Erreur inattendue sur la connexion WS de la room %s", code)
        room_manager.detach_connection(code, local_player_id)


__all__ = ["router"]
