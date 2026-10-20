"""Process-local rooms, private session proofs and bounded snapshot delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import WebSocket

from app.core.settings import settings
from app.game import engine
from app.game.serialize import serialize_state
from app.game.types import GameState


class RoomNotFoundError(Exception):
    pass


class UnknownParticipantError(Exception):
    pass


class CapacityError(Exception):
    pass


TERMINALS = {
    "session_revoked": (4401, "Session unavailable."),
    "player_kicked": (4403, "You were removed from the room."),
    "room_closed": (4404, "Room closed or unavailable."),
    "session_replaced": (4409, "Session opened elsewhere."),
    "rate_limited": (4429, "Rate limited."),
    "transport_failed": (1011, ""),
}


@dataclass
class Delivery:
    socket: WebSocket
    pending: dict | None = None
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    acknowledged: asyncio.Event = field(default_factory=asyncio.Event)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task | None = None
    stopped: bool = False
    ended: asyncio.Event = field(default_factory=asyncio.Event)
    terminal_code: str | None = None
    terminal_task: asyncio.Task | None = None


@dataclass
class Room:
    code: str
    state: GameState = field(default_factory=GameState)
    roles: dict[str, engine.Role] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    proofs: dict[str, bytes] = field(default_factory=dict)
    connections: dict[str, WebSocket] = field(default_factory=dict)
    deliveries: dict[WebSocket, Delivery] = field(default_factory=dict)
    presentateur_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False
    idle_since: float | None = None

    def role_of(self, local_player_id: str) -> engine.Role | None:
        return self.roles.get(local_player_id)


class RoomManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._rooms: dict[str, Room] = {}
        self.clock = clock
        self.preauth_connections = 0
        self.authenticated_connections: set[WebSocket] = set()

    def create_room(self, pseudo: str) -> tuple[Room, str, str]:
        if len(self._rooms) >= settings.max_rooms:
            raise CapacityError
        while True:
            code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(4))
            if code not in self._rooms:
                break
        room = Room(code=code, idle_since=self.clock())
        pid, token = self._membership(room, pseudo, "presentateur")
        room.presentateur_id = pid
        self._rooms[code] = room
        return room, pid, token

    def _membership(self, room: Room, pseudo: str, role: engine.Role) -> tuple[str, str]:
        pid, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        if role != "ecran-principal":
            if len(room.state.players) >= settings.max_players:
                raise CapacityError
            room.state = engine.add_player(room.state, pid, pseudo, is_presenter=role == "presentateur")
        elif sum(r == "ecran-principal" for r in room.roles.values()) >= settings.max_screens:
            raise CapacityError
        room.roles[pid] = role
        room.names[pid] = pseudo
        room.proofs[pid] = hashlib.sha256(token.encode()).digest()
        return pid, token

    def get_room(self, code: str) -> Room:
        room = self._rooms.get(code.upper())
        if room is None or room.closed:
            raise RoomNotFoundError
        return room

    def ensure_live(self, room: Room) -> None:
        """Called under the mutation lock, including between periodic sweeps."""
        if room.closed or self._rooms.get(room.code) is not room:
            raise RoomNotFoundError
        if room.idle_since is not None and self.clock() - room.idle_since >= settings.room_idle_ttl_seconds:
            self.close_room_locked(room)
            raise RoomNotFoundError

    def verify(self, room: Room, pid: str, token: str) -> None:
        digest = hashlib.sha256(token.encode()).digest()
        if not hmac.compare_digest(room.proofs.get(pid, bytes(32)), digest) or pid not in room.roles:
            raise UnknownParticipantError

    def join_room_locked(self, room: Room, pseudo: str, role: engine.Role) -> tuple[str, str]:
        self.ensure_live(room)
        return self._membership(room, pseudo, role)

    def close_room_locked(self, room: Room) -> list[WebSocket]:
        room.closed = True
        sockets = list(room.connections.values())
        for socket in sockets:
            self.invalidate_locked(room, socket, "room_closed")
        room.connections.clear()
        room.roles.clear()
        room.names.clear()
        room.proofs.clear()
        if self._rooms.get(room.code) is room:
            del self._rooms[room.code]
        return sockets

    def attach_locked(self, room: Room, pid: str, token: str, socket: WebSocket) -> WebSocket | None:
        self.ensure_live(room)
        self.verify(room, pid, token)
        if len(self.authenticated_connections) >= settings.max_authenticated_connections:
            raise CapacityError
        previous = room.connections.get(pid)
        if previous is not None:
            self.invalidate_locked(room, previous, "session_replaced")
        room.connections[pid] = socket
        self.authenticated_connections.add(socket)
        room.idle_since = None
        room.state = engine.set_player_connected(room.state, pid, True)
        delivery = Delivery(socket)
        room.deliveries[socket] = delivery
        delivery.task = asyncio.create_task(self._deliver(room, pid, delivery))
        self.publish_locked(room)
        return previous

    def publish_locked(self, room: Room) -> None:
        """One latest snapshot slot per socket; commits enqueue without network I/O."""
        state = serialize_state(room.state)
        for pid, socket in room.connections.items():
            delivery = room.deliveries[socket]
            delivery.pending = {"type": "room:state_sync", "payload": {
                "code": room.code, "role": room.roles[pid], "localPlayerId": pid, "state": state,
            }}
            delivery.wake.set()

    async def _deliver(self, room: Room, pid: str, delivery: Delivery) -> None:
        try:
            while not delivery.stopped:
                await delivery.wake.wait()
                delivery.wake.clear()
                message, delivery.pending = delivery.pending, None
                if message is not None:
                    await self.send(room, delivery.socket, message)
                    delivery.acknowledged.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.detach_connection(room, pid, delivery.socket)
            async with room.lock:
                self.invalidate_locked(room, delivery.socket, "transport_failed")

    async def send(self, room: Room, socket: WebSocket, message: dict[str, Any]) -> None:
        delivery = room.deliveries.get(socket)
        if delivery is None:
            await asyncio.wait_for(socket.send_json(message), settings.send_timeout_seconds)
        else:
            async with asyncio.timeout(settings.send_timeout_seconds):
                async with delivery.send_lock:
                    if delivery.stopped:
                        raise OSError("Socket is no longer active")
                    await socket.send_json(message)

    async def close_socket(self, socket: WebSocket, code: int, reason: str = "") -> None:
        try:
            await asyncio.wait_for(socket.close(code=code, reason=reason), settings.send_timeout_seconds)
        except Exception:
            pass

    def invalidate_locked(self, room: Room, socket: WebSocket, code: str) -> None:
        delivery = room.deliveries.get(socket)
        if delivery is not None and delivery.terminal_code is None:
            delivery.terminal_code = code
            delivery.stopped = True
            delivery.pending = None
            delivery.ended.set()

    async def terminal(self, room: Room | None, socket: WebSocket, code: str) -> None:
        delivery = room.deliveries.get(socket) if room else None
        if delivery is not None:
            self.invalidate_locked(room, socket, code)
            if delivery.terminal_task is None:
                delivery.terminal_task = asyncio.create_task(
                    self._terminal(socket, delivery.terminal_code, delivery)
                )
            await asyncio.shield(delivery.terminal_task)
        else:
            await self._terminal(socket, code, None)

    async def _terminal(self, socket: WebSocket, code: str, delivery: Delivery | None) -> None:
        if delivery:
            if delivery.task and delivery.task is not asyncio.current_task():
                delivery.task.cancel()
                await asyncio.gather(delivery.task, return_exceptions=True)
        close_code, message = TERMINALS[code]
        try:
            if code in ("player_kicked", "room_closed"):
                alias = "player:kicked" if code == "player_kicked" else "room:closed"
                await asyncio.wait_for(socket.send_json({"type": alias, "payload": {}}), settings.send_timeout_seconds)
            if code == "rate_limited":
                event = {"type": "error", "payload": {"code": code, "message": message}}
            else:
                event = {"type": "session:ended", "payload": {"code": code, "message": message}}
            if code != "transport_failed":
                await asyncio.wait_for(socket.send_json(event), settings.send_timeout_seconds)
        except Exception:
            pass
        await self.close_socket(socket, close_code, code)

    async def detach_connection(self, room: Room, pid: str, socket: WebSocket) -> None:
        async with room.lock:
            if room.connections.get(pid) is not socket:
                return
            del room.connections[pid]
            if room.closed:
                return
            room.state = engine.set_player_connected(room.state, pid, False)
            if not room.connections:
                room.idle_since = self.clock()
            self.publish_locked(room)

    async def release(self, room: Room, pid: str, socket: WebSocket) -> None:
        await self.detach_connection(room, pid, socket)
        delivery = room.deliveries.get(socket)
        if delivery and delivery.terminal_code:
            await self.terminal(room, socket, delivery.terminal_code)
        if delivery and delivery.task and delivery.task is not asyncio.current_task():
            delivery.task.cancel()
            await asyncio.gather(delivery.task, return_exceptions=True)
        if not delivery or not delivery.terminal_code:
            await self.close_socket(socket, 1000)
        room.deliveries.pop(socket, None)
        self.authenticated_connections.discard(socket)

    async def cleanup_once(self) -> None:
        for room in list(self._rooms.values()):
            async with room.lock:
                try:
                    self.ensure_live(room)
                except RoomNotFoundError:
                    pass

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.room_cleanup_interval_seconds)
            await self.cleanup_once()


room_manager = RoomManager()
