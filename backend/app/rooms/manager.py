"""Postgres-backed rooms with commit-gated caches and bounded socket delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import WebSocket

from app.core.settings import settings
from app.game import engine
from app.game.serialize import serialize_state
from app.game.types import GameState
from app.persistence.codec import FORMAT_VERSION, SavedGame, SavedSession, Snapshot, decode, encode
from app.persistence.store import CommitUnknown, Event, PersistenceUnavailable, RevisionConflict


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
    saved: Snapshot | None = field(default=None, repr=False)
    blocked: bool = False
    pending: Snapshot | None = field(default=None, repr=False)
    absent: set[str] = field(default_factory=set)
    heartbeat_at: float = 0

    def role_of(self, local_player_id: str) -> engine.Role | None:
        return self.roles.get(local_player_id)


class RoomManager:
    def __init__(self, store, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.store = store
        self._rooms: dict[str, Room] = {}
        self.clock = clock
        self.utcnow = utcnow
        self.started = False
        self.creation_lock = asyncio.Lock()
        self.pending_creations: dict[str, Room] = {}
        self.preauth_connections = 0
        self.authenticated_connections: set[WebSocket] = set()
        self.auth_reservations: set[WebSocket] = set()
        self.lost_transports: set[WebSocket] = set()
        self.readiness_checking = False

    async def create_room(self, pseudo: str) -> tuple[Room, str, str]:
        async with self.creation_lock:
            if not self.started or self.pending_creations:
                raise PersistenceUnavailable()
            if len(self._rooms) >= settings.max_rooms:
                raise CapacityError
            while True:
                code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(4))
                if code not in self._rooms and code not in self.pending_creations:
                    break
            room = Room(code=code, idle_since=self.clock())
            pid, token = self._membership(room, pseudo, "presentateur")
            room.presentateur_id = pid
            self.pending_creations[code] = room
            try:
                await self.commit_locked(room, room, "room:create", pid, liveness=True)
            except BaseException:
                if room.saved is not None and not room.blocked:
                    self._rooms[code] = room
                if not room.blocked:
                    self.pending_creations.pop(code, None)
                raise
            self.pending_creations.pop(code, None)
            self._rooms[code] = room
            if asyncio.current_task().cancelling():
                raise PersistenceUnavailable()
            return room, pid, token

    @staticmethod
    def candidate(room: Room) -> Room:
        return replace(room, roles=dict(room.roles), names=dict(room.names), proofs=dict(room.proofs),
                       connections={}, deliveries={}, absent=set())

    def snapshot(self, room: Room, candidate: Room, kind: str | None, *, liveness=False,
                 status="live") -> Snapshot:
        previous = room.saved
        now = self.utcnow()
        members = {str(s.participant_id): s for s in previous.sessions} if previous else {}
        for pid, old in list(members.items()):
            if old.status == "active" and (pid not in candidate.roles or status != "live"):
                members[pid] = old.model_copy(update={"status": "revoked", "revoked_at": now})
        for pid, role in candidate.roles.items():
            old = members.get(pid)
            members[pid] = SavedSession(
                participant_id=uuid.UUID(pid), name=candidate.names[pid], role=role,
                proof_digest=candidate.proofs[pid].hex(),
                status="active" if status == "live" else "revoked",
                created_at=old.created_at if old else now,
                revoked_at=None if status == "live" else now,
            )
        signal = now if liveness or previous is None else previous.last_liveness_at
        return Snapshot(
            format_version=FORMAT_VERSION, room_id=previous.room_id if previous else uuid.uuid4(),
            game_id=previous.game_id if previous and kind != "game:reset" else uuid.uuid4(),
            write_id=uuid.uuid4(), code=room.code, revision=previous.revision + 1 if previous else 1,
            status=status, created_at=previous.created_at if previous else now,
            closed_at=None if status == "live" else now,
            idle_deadline_utc=signal + timedelta(seconds=settings.room_idle_ttl_seconds)
                if liveness or previous is None else previous.idle_deadline_utc,
            last_liveness_at=signal, presenter_id=uuid.UUID(candidate.presentateur_id),
            state=SavedGame.from_game(candidate.state), sessions=tuple(members.values()),
        )

    def install(self, room: Room, saved: Snapshot) -> None:
        if room.saved is None or room.saved.last_liveness_at != saved.last_liveness_at:
            room.heartbeat_at = self.clock()
        room.saved = saved
        room.state = saved.state.to_game()
        active = {str(s.participant_id): s for s in saved.sessions if s.status == "active"}
        room.roles = {pid: s.role for pid, s in active.items()}
        room.names = {pid: s.name for pid, s in active.items()}
        room.proofs = {pid: bytes.fromhex(s.proof_digest) for pid, s in active.items()}
        room.presentateur_id = str(saved.presenter_id)
        room.closed = saved.status != "live"

    async def commit_locked(self, room: Room, candidate: Room, kind: str | None,
                            actor: str | None = None, *, liveness=False, status="live") -> None:
        if room.blocked:
            raise PersistenceUnavailable()
        saved = self.snapshot(room, candidate, kind, liveness=liveness, status=status)
        # Validate before handing anything to the repository, including test doubles.
        saved = decode(encode(saved))
        expected = room.saved.revision if room.saved else 0
        event = Event(kind, self.utcnow(), uuid.UUID(actor) if actor else None) if kind else None
        try:
            await self.store.write(saved, expected, event)
        except (CommitUnknown, RevisionConflict):
            room.blocked, room.pending = True, saved
            try:
                outcome = await self.store.reconcile(saved, expected)
            except (Exception, asyncio.CancelledError):
                outcome = "blocked"
            if outcome == "committed":
                self.install(room, saved)
                room.blocked, room.pending = False, None
                # Let the caller complete synchronous authority/revocation
                # bookkeeping even when cancellation caused the lost reply.
                return
            elif outcome == "not_committed":
                room.blocked, room.pending = False, None
            raise PersistenceUnavailable() from None
        self.install(room, saved)

    async def start(self) -> None:
        self.started = False
        await self.store.check()
        restored = await self.store.load_live()
        if len(restored) > settings.max_rooms:
            raise PersistenceUnavailable()
        self._rooms.clear()
        self.pending_creations.clear()
        for saved in restored:
            saved = decode(encode(saved))
            room = Room(saved.code)
            self.install(room, saved)
            if (len(room.state.players) > settings.max_players
                    or sum(r == "ecran-principal" for r in room.roles.values()) > settings.max_screens
                    or len(room.state.themes) > settings.max_themes or room.code in self._rooms):
                raise PersistenceUnavailable()
            self._rooms[room.code] = room
            remaining = max(0, (saved.idle_deadline_utc - self.utcnow()).total_seconds())
            room.idle_since = self.clock() - settings.room_idle_ttl_seconds + remaining
            if remaining == 0:
                await self.close_room_locked(room, expired=True)
                continue
            candidate = self.candidate(room)
            for pid in room.roles:
                candidate.state = engine.set_player_connected(candidate.state, pid, False)
            if candidate.state != room.state:
                await self.commit_locked(room, candidate, "room:recover")
        self.started = True

    async def ready(self) -> bool:
        def unavailable():
            return (not self.started or self.pending_creations or any(
                r.blocked or r.absent or (r.connections and self.clock() - r.heartbeat_at > 60)
                for r in self._rooms.values()))

        if unavailable() or self.readiness_checking:
            return False
        self.readiness_checking = True
        try:
            async with asyncio.timeout(2):
                await self.store.check()
        except Exception:
            return False
        finally:
            self.readiness_checking = False
        return not unavailable()

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
        if not self.started:
            raise PersistenceUnavailable()
        room = self._rooms.get(code.upper())
        if room is None or room.closed:
            raise RoomNotFoundError
        return room

    async def ensure_live(self, room: Room) -> None:
        """Called under the mutation lock, including between periodic sweeps."""
        if room.closed or self._rooms.get(room.code) is not room:
            raise RoomNotFoundError
        if room.idle_since is not None and self.clock() - room.idle_since >= settings.room_idle_ttl_seconds:
            await self.close_room_locked(room, expired=True)
            raise RoomNotFoundError
        if room.blocked or room.absent:
            raise PersistenceUnavailable()

    def verify(self, room: Room, pid: str, token: str) -> None:
        digest = hashlib.sha256(token.encode()).digest()
        if not hmac.compare_digest(room.proofs.get(pid, bytes(32)), digest) or pid not in room.roles:
            raise UnknownParticipantError

    async def join_room_locked(self, room: Room, pseudo: str, role: engine.Role) -> tuple[str, str]:
        await self.ensure_live(room)
        candidate = self.candidate(room)
        pid, token = self._membership(candidate, pseudo, role)
        await self.commit_locked(room, candidate, "room:join", pid, liveness=bool(room.connections))
        # Membership is confirmed: never turn a separate presence failure into
        # a failed join that discards the only copy of its bearer proof.
        if room.absent:
            try:
                await self.reconcile_presence_locked(room)
            except (PersistenceUnavailable, asyncio.CancelledError):
                room.blocked = True
        return pid, token

    async def close_room_locked(self, room: Room, *, expired=False) -> list[WebSocket]:
        await self.commit_locked(room, self.candidate(room), "room:expire" if expired else "room:quit",
                                 status="expired" if expired else "closed")
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

    def reserve_auth(self, socket: WebSocket) -> None:
        if len(self.authenticated_connections) + len(self.auth_reservations) >= settings.max_authenticated_connections:
            raise CapacityError
        self.auth_reservations.add(socket)

    async def attach_locked(self, room: Room, pid: str, token: str, socket: WebSocket) -> WebSocket | None:
        # The endpoint reserves before lock wait; direct callers reserve here.
        if socket not in self.auth_reservations:
            self.reserve_auth(socket)
        try:
            return await self._attach_locked(room, pid, token, socket)
        finally:
            self.auth_reservations.discard(socket)

    async def _attach_locked(self, room: Room, pid: str, token: str, socket: WebSocket) -> WebSocket | None:
        await self.ensure_live(room)
        self.verify(room, pid, token)
        previous = room.connections.get(pid)
        candidate = self.candidate(room)
        candidate.state = engine.set_player_connected(candidate.state, pid, True)
        try:
            await self.commit_locked(room, candidate, "session:attach", pid, liveness=True)
        except BaseException:
            # A confirmed write interrupted before authority installation still
            # needs a durable absence. Unknown writes remain blocked for restore.
            if not room.blocked and room.saved.state == SavedGame.from_game(candidate.state):
                await self.reconcile_presence_locked(room)
            raise
        if room.absent or socket in self.lost_transports or asyncio.current_task().cancelling():
            # Reconcile ALL missing transports, including this committed attach
            # which was never installed, not just the participant that detached.
            await self.reconcile_presence_locked(room)
            raise PersistenceUnavailable()
        if previous is not None:
            self.invalidate_locked(room, previous, "session_replaced")
        room.connections[pid] = socket
        self.authenticated_connections.add(socket)
        room.idle_since = None
        delivery = Delivery(socket)
        room.deliveries[socket] = delivery
        delivery.task = asyncio.create_task(self._deliver(room, pid, delivery))
        self.publish_locked(room)
        return previous

    async def reconcile_presence_locked(self, room: Room) -> None:
        if room.closed:
            room.absent.clear()
            return
        candidate = self.candidate(room)
        absent = {p.id for p in room.state.players if p.connected and p.id not in room.connections}
        observed = set(room.absent)
        room.absent.update(absent)
        for pid in absent:
            candidate.state = engine.set_player_connected(candidate.state, pid, False)
        try:
            if candidate.state != room.state or observed:
                await self.commit_locked(room, candidate, "session:detach", liveness=True)
        except BaseException:
            room.blocked = True
            raise
        room.absent.difference_update(observed | absent)
        if not room.connections and room.idle_since is None:
            room.idle_since = self.clock()
        self.publish_locked(room)

    def publish_locked(self, room: Room) -> None:
        """One latest snapshot slot per socket; commits enqueue without network I/O."""
        if room.absent or room.blocked:
            return
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
                async with room.lock:
                    delivery.wake.clear()
                    message, delivery.pending = delivery.pending, None
                    if room.blocked or room.absent:
                        # Discard stale queued presence; reconciliation enqueues
                        # the next committed snapshot without polling this slot.
                        message = None
                if message is not None:
                    if await self.send(room, delivery.socket, message):
                        delivery.acknowledged.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.detach_connection(room, pid, delivery.socket)
            async with room.lock:
                self.invalidate_locked(room, delivery.socket, "transport_failed")

    async def send(self, room: Room, socket: WebSocket, message: dict[str, Any]) -> bool:
        delivery = room.deliveries.get(socket)
        snapshot = message["type"] == "room:state_sync"
        if delivery is None:
            if snapshot:
                return False
            await asyncio.wait_for(socket.send_json(message), settings.send_timeout_seconds)
        else:
            async with asyncio.timeout(settings.send_timeout_seconds):
                async with delivery.send_lock:
                    if snapshot and (room.blocked or room.absent or room.closed or delivery.stopped
                            or room.deliveries.get(socket) is not delivery
                            or room.connections.get(message["payload"]["localPlayerId"]) is not socket):
                        return False
                    if delivery.stopped:
                        raise OSError("Socket is no longer active")
                    # No await after snapshot validation before entering send_json.
                    # A transport send already entered cannot be recalled later.
                    await socket.send_json(message)
        return True

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

    def lose_connection(self, room: Room, pid: str, socket: WebSocket) -> bool:
        # No await before releasing physical authority: DB/lock failure cannot
        # keep a dead transport eligible, or detach a replacement socket.
        if room.connections.get(pid) is not socket:
            if socket in self.auth_reservations:
                self.lost_transports.add(socket)
            return False
        del room.connections[pid]
        room.absent.add(pid)
        self.invalidate_locked(room, socket, "transport_failed")
        self.authenticated_connections.discard(socket)
        if not room.connections:
            room.idle_since = self.clock()
        return True

    async def detach_connection(self, room: Room, pid: str, socket: WebSocket) -> None:
        lost = self.lose_connection(room, pid, socket)
        if not lost and not room.absent:
            return
        async with room.lock:
            try:
                await self.reconcile_presence_locked(room)
            except (PersistenceUnavailable, asyncio.CancelledError):
                room.blocked = True
                return

    async def release(self, room: Room, pid: str, socket: WebSocket,
                      *, transport_close: tuple[int, str] | None = None,
                      transport_disconnected: bool = False) -> None:
        await self.detach_connection(room, pid, socket)
        delivery = room.deliveries.get(socket)
        if transport_close:
            # Reader-selected overload/size causes outrank cleanup failures.
            # Do not let transport_failed emit a competing close first.
            if delivery and delivery.task:
                delivery.task.cancel()
                await asyncio.gather(delivery.task, return_exceptions=True)
            if transport_close[0] == 4429:
                try:
                    await asyncio.wait_for(socket.send_json({"type": "error", "payload": {
                        "code": "rate_limited", "message": "Rate limited.",
                    }}), settings.send_timeout_seconds)
                except Exception:
                    pass
            await self.close_socket(socket, *transport_close)
        elif not transport_disconnected and delivery and delivery.terminal_code:
            await self.terminal(room, socket, delivery.terminal_code)
        if delivery and delivery.task and delivery.task is not asyncio.current_task():
            delivery.task.cancel()
            await asyncio.gather(delivery.task, return_exceptions=True)
        if not transport_disconnected and not transport_close and (not delivery or not delivery.terminal_code):
            await self.close_socket(socket, 1000)
        room.deliveries.pop(socket, None)
        self.authenticated_connections.discard(socket)
        self.lost_transports.discard(socket)

    async def cleanup_once(self) -> None:
        for room in list(self._rooms.values()):
            async with room.lock:
                try:
                    await self.ensure_live(room)
                    if room.connections:
                        try:
                            await self.commit_locked(room, self.candidate(room), None, liveness=True)
                        except PersistenceUnavailable:
                            room.blocked = True
                except RoomNotFoundError:
                    pass
                except PersistenceUnavailable:
                    pass

    async def cleanup_loop(self) -> None:
        deadline = self.clock()
        while True:
            deadline += min(60, settings.room_cleanup_interval_seconds)
            await asyncio.sleep(max(0, deadline - self.clock()))
            await self.cleanup_once()
            # Do not accumulate sweep/DB duration into the heartbeat period or
            # replay missed ticks after an outage.
            deadline = max(deadline, self.clock() - min(60, settings.room_cleanup_interval_seconds))


# No repository is selected and no connection is made at import time.
room_manager = RoomManager(None)
