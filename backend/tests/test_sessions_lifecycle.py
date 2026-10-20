"""Deterministic socket races and monotonic room lifetime boundaries."""

import asyncio
import json
from unittest.mock import patch

import pytest
from starlette.datastructures import Headers, QueryParams

from app.api import rooms, ws
from app.core.limits import TokenBucket
from app.core.settings import Settings, settings
from app.game import engine
from app.main import create_app
from app.rooms.manager import CapacityError, RoomManager, RoomNotFoundError
from fastapi.testclient import TestClient


class Socket:
    def __init__(self):
        self.headers = Headers({"origin": "http://localhost:5173"})
        self.query_params = QueryParams()
        self.scope = {}
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.closes = []
        self.block = None
        self.started = asyncio.Event()
        self.fail = False
        self.close_block = None
        self.lock = None

    async def accept(self):
        pass

    async def receive(self):
        return await self.incoming.get()

    async def send_json(self, message):
        assert self.lock is None or not self.lock.locked(), "Network under mutation lock"
        self.started.set()
        if self.block is not None:
            await self.block.wait()
        if self.fail:
            raise OSError("Simulated send failure")
        await self.outgoing.put(message)

    async def close(self, code=1000, reason=""):
        assert self.lock is None or not self.lock.locked(), "Close under mutation lock"
        self.closes.append((code, reason))
        if self.close_block is not None:
            await self.close_block.wait()

    def command(self, event, payload=None):
        self.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps({
            "type": event, "payload": payload or {},
        })})

    async def sync(self):
        message = await asyncio.wait_for(self.outgoing.get(), 1)
        assert message["type"] == "room:state_sync"
        return message["payload"]["state"]


async def attach(manager, room, pid, token, socket):
    socket.lock = room.lock
    async with room.lock:
        previous = manager.attach_locked(room, pid, token, socket)
    await asyncio.wait_for(room.deliveries[socket].acknowledged.wait(), 1)
    return previous


@pytest.mark.asyncio
async def test_replaced_socket_late_failure_and_detach_preserve_latest():
    manager = RoomManager()
    room, pid, token = manager.create_room("Host")
    old, latest = Socket(), Socket()
    await attach(manager, room, pid, token, old)
    old.fail = True
    assert await attach(manager, room, pid, token, latest) is old
    await manager.detach_connection(room, pid, old)
    await manager.terminal(room, old, "session_replaced")
    await manager.release(room, pid, old)
    assert room.connections[pid] is latest
    assert room.state.players[0].connected
    assert old.closes == [(4409, "session_replaced")]
    assert latest in manager.authenticated_connections
    await manager.release(room, pid, latest)
    assert not manager.authenticated_connections


@pytest.mark.asyncio
async def test_inflight_old_sender_failure_cannot_detach_replacement():
    manager = RoomManager()
    room, pid, token = manager.create_room("Host")
    old, latest = Socket(), Socket()
    old.block = asyncio.Event()
    old.lock = room.lock
    async with room.lock:
        manager.attach_locked(room, pid, token, old)
    await old.started.wait()
    await attach(manager, room, pid, token, latest)
    old.fail = True
    old.block.set()
    await asyncio.wait_for(room.deliveries[old].task, 1)
    assert room.connections[pid] is latest
    assert room.state.players[0].connected
    await manager.release(room, pid, old)
    assert old.closes == [(4409, "session_replaced")]
    await manager.release(room, pid, latest)


@pytest.mark.asyncio
async def test_double_command_only_commits_one_phase_transition(monkeypatch):
    manager = RoomManager()
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "global_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    room, host, token = manager.create_room("Host")
    player, _ = manager.join_room_locked(room, "Alice", "joueur")
    manager.join_room_locked(room, "Bob", "joueur")
    room.state = engine.add_theme(room.state, "Cinema", "presentateur")
    room.state = engine.set_player_connected(room.state, player, True)
    room.state = engine.start_game(room.state, "presentateur")
    room.state = engine.reveal_choice(room.state, "presentateur")
    room.state = engine.select_theme(room.state, 0, "joueur", player)
    socket = Socket()
    socket.command("session:auth", {"localPlayerId": host, "sessionToken": token})
    running = asyncio.create_task(ws.websocket_endpoint(socket, room.code))
    await socket.sync()
    socket.command("timer:start")
    socket.command("timer:start")
    messages = [await asyncio.wait_for(socket.outgoing.get(), 1) for _ in range(2)]
    assert sorted(message["type"] for message in messages) == ["error", "room:state_sync"]
    assert next(m for m in messages if m["type"] == "error")["payload"]["code"] == "invalid_phase"
    assert room.state.tunnel_sub_phase == "question"
    assert room.state.themes[0].progress_value == 0
    socket.incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})
    await asyncio.wait_for(running, 1)


@pytest.mark.asyncio
async def test_stale_command_queued_before_replacement_cannot_mutate(monkeypatch):
    manager = RoomManager()
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "global_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    room, pid, token = manager.create_room("Host")
    old, latest = Socket(), Socket()
    old.command("session:auth", {"localPlayerId": pid, "sessionToken": token})
    running = asyncio.create_task(ws.websocket_endpoint(old, room.code))
    await old.sync()
    # Hold the mutation lock while both an obsolete command and replacement
    # become runnable. Replacement is installed before the command may commit.
    async with room.lock:
        old.command("theme:add", {"label": "Must not commit"})
        manager.attach_locked(room, pid, token, latest)
    await asyncio.wait_for(running, 1)
    assert not room.state.themes
    assert room.connections[pid] is latest
    assert room.state.players[0].connected
    assert old.closes == [(4409, "session_replaced")]
    await manager.release(room, pid, latest)


@pytest.mark.asyncio
async def test_stalled_send_has_one_pending_slot_and_does_not_block_fast_recipient(monkeypatch):
    monkeypatch.setattr(settings, "send_timeout_seconds", .03)
    manager = RoomManager()
    room, host, token = manager.create_room("Host")
    player, player_token = manager.join_room_locked(room, "Alice", "joueur")
    slow, fast = Socket(), Socket()
    slow.block = asyncio.Event()
    slow.lock = room.lock
    async with room.lock:
        manager.attach_locked(room, host, token, slow)
    await slow.started.wait()
    await attach(manager, room, player, player_token, fast)
    await fast.sync()
    async with room.lock:
        for index in range(100):
            room.state = engine.rename_player(room.state, "joueur", player, f"Name{index}")
            manager.publish_locked(room)
        assert isinstance(room.deliveries[slow].pending, dict)
    latest = await fast.sync()
    assert latest["players"][1]["name"] == "Name99"
    await asyncio.wait_for(room.deliveries[slow].ended.wait(), 1)
    assert host not in room.connections
    assert room.connections[player] is fast
    slow.block.set()
    await manager.release(room, host, slow)
    await manager.release(room, player, fast)
    assert slow.closes[0][0] == 1011


@pytest.mark.asyncio
async def test_terminal_invalidation_wins_over_parallel_cleanup_and_preserves_capacity(monkeypatch):
    monkeypatch.setattr(settings, "max_authenticated_connections", 2)
    manager = RoomManager()
    room, pid, token = manager.create_room("Host")
    first, second, third = Socket(), Socket(), Socket()
    await attach(manager, room, pid, token, first)
    await attach(manager, room, pid, token, second)
    with pytest.raises(CapacityError):
        async with room.lock:
            manager.attach_locked(room, pid, token, third)
    assert room.connections[pid] is second
    await asyncio.gather(manager.terminal(room, first, "session_replaced"),
                         manager.release(room, pid, first))
    assert first.closes == [(4409, "session_replaced")]
    await manager.release(room, pid, second)
    assert not room.deliveries and not manager.authenticated_connections


@pytest.mark.asyncio
async def test_slow_terminal_close_is_bounded_and_cannot_restore_revoked_proof(monkeypatch):
    monkeypatch.setattr(settings, "send_timeout_seconds", .02)
    manager = RoomManager()
    room, pid, token = manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    socket.block = asyncio.Event()
    socket.close_block = asyncio.Event()
    async with room.lock:
        sockets = manager.close_room_locked(room)
    assert not room.proofs and room.closed
    await asyncio.wait_for(manager.terminal(room, sockets[0], "room_closed"), .2)
    await manager.release(room, pid, socket)
    assert socket.closes == [(4404, "room_closed")]
    assert not manager.authenticated_connections


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,close_code", [
    ("session_replaced", 4409), ("player_kicked", 4403), ("room_closed", 4404),
])
async def test_blocked_error_send_under_send_lock_preserves_terminal_and_replacement(monkeypatch, reason, close_code):
    monkeypatch.setattr(settings, "send_timeout_seconds", .03)

    class ErrorBlockedSocket(Socket):
        async def send_json(self, message):
            if message["type"] == "error":
                self.error_started.set()
                await asyncio.Event().wait()
            await super().send_json(message)

    manager = RoomManager()
    room, host, _ = manager.create_room("Host")
    pid, token = manager.join_room_locked(room, "Alice", "joueur")
    old, latest = ErrorBlockedSocket(), Socket()
    old.error_started = asyncio.Event()
    await attach(manager, room, pid, token, old)
    await old.sync()
    error_send = asyncio.create_task(manager.send(room, old, {
        "type": "error", "payload": {"code": "invalid_payload", "message": "Invalid message."},
    }))
    await asyncio.wait_for(old.error_started.wait(), .2)
    assert room.deliveries[old].send_lock.locked()
    if reason == "session_replaced":
        await attach(manager, room, pid, token, latest)
    else:
        async with room.lock:
            if reason == "room_closed":
                manager.close_room_locked(room)
            else:
                room.state = engine.remove_player(room.state, 1, "presentateur")
                for mapping in (room.proofs, room.roles, room.names, room.connections):
                    mapping.pop(pid, None)
                manager.invalidate_locked(room, old, reason)
    await asyncio.wait_for(asyncio.gather(
        manager.terminal(room, old, reason), manager.release(room, pid, old),
    ), .3)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(error_send, .2)
    assert old.closes == [(close_code, reason)]
    messages = []
    while not old.outgoing.empty():
        messages.append(old.outgoing.get_nowait())
    assert messages[-1]["type"] == "session:ended"
    assert messages[-1]["payload"]["code"] == reason
    assert old not in manager.authenticated_connections
    if reason == "session_replaced":
        assert room.connections[pid] is latest
        assert room.state.players[1].connected
        manager.verify(room, pid, token)
        await manager.release(room, pid, latest)
    else:
        assert pid not in room.proofs and pid not in room.connections
    assert host != pid


@pytest.mark.asyncio
async def test_ttl_exact_boundary_auth_and_sweep_revoke(monkeypatch):
    monkeypatch.setattr(settings, "room_idle_ttl_seconds", 10)
    now = [0.0]
    manager = RoomManager(clock=lambda: now[0])
    room, pid, token = manager.create_room("Host")
    now[0] = 9.999
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    now[0] = 100
    await manager.cleanup_once()
    assert manager.get_room(room.code) is room
    await manager.release(room, pid, socket)
    assert room.idle_since == 100
    now[0] = 109.999
    manager.verify(room, pid, token)
    manager.join_room_locked(room, "Screen", "ecran-principal")
    assert room.idle_since == 100  # Neither REST proof nor membership extends TTL.
    now[0] = 110
    async with room.lock:
        with pytest.raises(RoomNotFoundError):
            manager.attach_locked(room, pid, token, Socket())
    assert room.closed and not room.proofs and not manager._rooms
    other, _, _ = manager.create_room("Other")
    now[0] = 120
    await manager.cleanup_once()
    assert other.closed and not manager._rooms


@pytest.mark.asyncio
async def test_authenticated_screen_alone_keeps_room_alive(monkeypatch):
    monkeypatch.setattr(settings, "room_idle_ttl_seconds", 10)
    now = [0.0]
    manager = RoomManager(clock=lambda: now[0])
    room, _, _ = manager.create_room("Host")
    screen, proof = manager.join_room_locked(room, "Screen", "ecran-principal")
    socket = Socket()
    await attach(manager, room, screen, proof, socket)
    now[0] = 100
    await manager.cleanup_once()
    assert room.idle_since is None
    assert all(not player.connected for player in room.state.players)
    await manager.release(room, screen, socket)
    now[0] = 110
    await manager.cleanup_once()
    assert room.closed


def test_startup_applies_configured_process_global_bucket_policies():
    config = Settings(rest_rate_per_second=.1, rest_rate_burst=1,
                      ws_upgrade_rate_per_second=.2, ws_upgrade_rate_burst=2,
                      ws_global_rate_per_second=.3, ws_global_rate_burst=3)
    with patch.dict(vars(settings), vars(settings).copy()):
        with TestClient(create_app(config)) as client:
            assert (rooms.rest_bucket.rate, rooms.rest_bucket.burst) == (.1, 1)
            assert (ws.upgrade_bucket.rate, ws.upgrade_bucket.burst) == (.2, 2)
            assert (ws.global_bucket.rate, ws.global_bucket.burst) == (.3, 3)
            assert client.post("/api/rooms", json={}).status_code == 422
            denied = client.post("/api/rooms", json={})
            assert denied.status_code == 429
            assert denied.headers["retry-after"] == "10"
