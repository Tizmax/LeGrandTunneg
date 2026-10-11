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
    websocket: WebSocket,
    code: str,
    role: str,
    local_player_id: str,
    state: GameState,
    presentateur_name: str | None,
) -> None:
    await websocket.send_json(
        {
            "type": "room:state_sync",
            "payload": {
                "code": code,
                "role": role,
                "localPlayerId": local_player_id,
                "state": serialize_state(state, presentateur_name),
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


def _h_game_start(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.start_game(state, role)


def _h_choice_reveal(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.reveal_choice(state, role)


def _h_theme_select(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.select_theme(state, _require_int(payload, "index"), role, pid)


def _h_timer_start(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.start_timer(state, role)


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


def _h_game_end_early(state: GameState, payload: dict, role: str, pid: str) -> GameState:
    return engine.end_game_early(state, role)


def _require_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise engine.GameError("invalid_payload", f"Champ '{key}' manquant ou invalide.")
    return value


_HANDLERS: dict[str, Callable[[GameState, dict, str, str], GameState]] = {
    "theme:add": _h_theme_add,
    "theme:remove": _h_theme_remove,
    "player:remove": _h_player_remove,
    "game:start": _h_game_start,
    # "player:rename" est traité à part : un Présentateur/Écran principal
    # n'a pas d'entrée dans GameState.players (voir app/rooms/manager.py),
    # son nom d'affichage vit uniquement dans Room.names.
    "choice:reveal": _h_choice_reveal,
    "theme:select": _h_theme_select,
    "timer:start": _h_timer_start,
    "answer:good": _h_answer_good,
    "answer:bad": _h_answer_bad,
    "answer:pass": _h_answer_pass,
    "answer:continue": _h_answer_continue,
    "answer:vault": _h_answer_vault,
    "game:reset": _h_game_reset,
    # Le Présentateur peut mettre fin à la partie en cours à tout moment
    # (visible sur tous les écrans de jeu) : ramène tout le monde au lobby,
    # joueurs/thèmes conservés, scores remis à zéro. Différent de
    # "room:quit" qui ferme toute la room (voir boucle principale ci-dessous).
    "game:end_early": _h_game_end_early,
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

    # Un Joueur qui se (re)connecte redevient `connected=True` — pertinent
    # après une déconnexion (voir bloc except ci-dessous) : son tour n'est
    # plus sauté et les autres clients le voient réapparaître comme présent.
    # On ne broadcast QUE si l'état a réellement changé (set_player_connected
    # renvoie le même objet état si déjà dans le bon état) : sinon, chaque
    # connexion initiale (joueur déjà connecté=True par défaut depuis
    # add_player) enverrait un state_sync parasite à toute la room, avant
    # même l'envoi du state_sync initial propre à ce client — désynchronisant
    # l'ordre des messages reçus par les autres clients déjà connectés.
    if role == "joueur":
        async with room.lock:
            previous_state = room.state
            room.state = engine.set_player_connected(room.state, local_player_id, True)
            changed = room.state is not previous_state
        if changed:
            await _broadcast_state(code)

    await _send_state_sync(
        websocket, code, role, local_player_id, room.state, room.presentateur_name
    )

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

            if msg_type == "player:rename":
                name = payload.get("name", "")
                async with room.lock:
                    try:
                        if role == "joueur":
                            room.state = engine.rename_player(
                                room.state, role, local_player_id, name
                            )
                        else:
                            room_manager.rename_participant(code, local_player_id, name)
                    except engine.GameError as exc:
                        await _send_error(websocket, exc.code, exc.message)
                        continue
                    except (ValueError, UnknownParticipantError) as exc:
                        await _send_error(websocket, "invalid_payload", str(exc))
                        continue
                    await _broadcast_state(code)
                continue

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
        await _mark_disconnected(code, role, local_player_id)
    except Exception:
        logger.exception("Erreur inattendue sur la connexion WS de la room %s", code)
        room_manager.detach_connection(code, local_player_id)
        await _mark_disconnected(code, role, local_player_id)


async def _mark_disconnected(code: str, role: str, local_player_id: str) -> None:
    """Marque un Joueur comme absent (voir `engine.set_player_connected`) —
    reste dans `state.players` pour le classement final, son tour est
    simplement sauté tant qu'il n'est pas revenu. Ne s'applique pas au
    Présentateur/Écran principal, absents de `state.players`."""
    if role != "joueur":
        return
    try:
        room = room_manager.get_room(code)
    except RoomNotFoundError:
        return
    async with room.lock:
        room.state = engine.set_player_connected(room.state, local_player_id, False)
    await _broadcast_state(code)


__all__ = ["router"]
