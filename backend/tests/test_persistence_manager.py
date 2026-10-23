"""Offline manager failure matrix. Injected doubles cannot prove Postgres durability."""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings, settings
from app.api import ws
from app.core.limits import TokenBucket
from app.game import engine
from app.main import create_app
from app.persistence.config import DatabaseConfig
from app.persistence.store import CommitUnknown, PersistenceUnavailable, RevisionConflict
from app.rooms.manager import RoomManager
from tests.persistence_double import StrictStore, manager_for_test
from tests.test_sessions_lifecycle import Socket, attach
from app.rooms.manager import CapacityError


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "join", "attach", "close", "command", "reset"])
async def test_known_failure_leaves_cache_authority_and_archives_unchanged(operation):
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    saved, state = room.saved, room.state
    before = (dict(room.roles), dict(room.proofs), list(manager.store.archives))
    manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
    with pytest.raises(PersistenceUnavailable):
        if operation == "create":
            await manager.create_room("Other")
        elif operation == "join":
            await manager.join_room_locked(room, "Alice", "joueur")
        elif operation == "attach":
            await manager.attach_locked(room, pid, token, Socket())
        elif operation == "close":
            await manager.close_room_locked(room)
        else:
            candidate = manager.candidate(room)
            candidate.state = engine.add_theme(room.state, "Cinema", "presentateur")
            await manager.commit_locked(room, candidate, "game:reset" if operation == "reset" else "theme:add", pid)
    assert room.saved == saved and room.state == state
    assert (room.roles, room.proofs, manager.store.archives) == before
    assert not room.connections and not manager.authenticated_connections
    assert not manager.pending_creations


@pytest.mark.asyncio
async def test_join_and_attach_wait_for_commit_before_install_or_publish():
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        entered.set()
        await proceed.wait()
        await original(*args)

    manager.store.write = delayed
    task = asyncio.create_task(manager.attach_locked(room, pid, token, socket))
    await entered.wait()
    assert not room.connections and not room.deliveries and not room.state.players[0].connected
    assert socket.outgoing.empty()
    proceed.set()
    await task
    await socket.sync()
    assert room.state.players[0].connected
    await manager.release(room, pid, socket)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [CommitUnknown, RevisionConflict])
@pytest.mark.parametrize("outcome", ["committed", "not_committed", "blocked"])
async def test_ambiguous_write_single_readback_no_replay(failure, outcome):
    manager = manager_for_test()
    room, pid, _ = await manager.create_room("Host")
    before = room.saved
    candidate = manager.candidate(room)
    candidate.state = engine.add_theme(room.state, "Cinema", "presentateur")
    manager.store.write = AsyncMock(side_effect=failure())
    manager.store.reconcile = AsyncMock(return_value=outcome)
    if outcome == "committed":
        await manager.commit_locked(room, candidate, "theme:add", pid)
    else:
        with pytest.raises(PersistenceUnavailable):
            await manager.commit_locked(room, candidate, "theme:add", pid)
    assert manager.store.write.await_count == manager.store.reconcile.await_count == 1
    assert room.blocked == (outcome == "blocked")
    assert (room.saved != before) == (outcome == "committed")
    assert await manager.ready() == (outcome != "blocked")


@pytest.mark.asyncio
async def test_unknown_creation_reserves_code_and_never_returns_proof():
    manager = manager_for_test()
    manager.store.write = AsyncMock(side_effect=CommitUnknown())
    manager.store.reconcile = AsyncMock(return_value="blocked")
    with pytest.raises(PersistenceUnavailable):
        await manager.create_room("Host")
    assert not manager._rooms and len(manager.pending_creations) == 1
    with pytest.raises(PersistenceUnavailable):
        await manager.create_room("Other")
    assert manager.store.write.await_count == 1
    assert not await manager.ready()


@pytest.mark.asyncio
async def test_cancelled_readback_preserves_unknown_block():
    manager = manager_for_test()
    room, pid, _ = await manager.create_room("Host")
    manager.store.write = AsyncMock(side_effect=CommitUnknown())
    entered = asyncio.Event()

    async def readback(*args):
        entered.set()
        await asyncio.Event().wait()

    manager.store.reconcile = readback
    task = asyncio.create_task(manager.commit_locked(room, manager.candidate(room), "session:attach", pid))
    await entered.wait()
    task.cancel()
    with pytest.raises(PersistenceUnavailable):
        await task
    assert room.blocked and room.pending is not None
    assert not await manager.ready()


@pytest.mark.asyncio
async def test_disconnect_releases_authority_before_lock_and_db_failure():
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
    async with room.lock:
        task = asyncio.create_task(manager.detach_connection(room, pid, socket))
        await asyncio.sleep(0)
        assert pid not in room.connections and pid in room.absent
        assert socket not in manager.authenticated_connections
        assert not task.done()
    await task
    assert room.blocked and room.absent
    assert not await manager.ready()
    await manager.release(room, pid, socket)
    assert not room.deliveries


@pytest.mark.asyncio
async def test_detach_during_commit_suppresses_candidate_delivery_and_then_commits_absence():
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    await socket.sync()
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        entered.set()
        await proceed.wait()
        await original(*args)

    manager.store.write = delayed

    async def mutate():
        async with room.lock:
            candidate = manager.candidate(room)
            candidate.state = engine.add_theme(room.state, "Cinema", "presentateur")
            await manager.commit_locked(room, candidate, "theme:add", pid)
            manager.publish_locked(room)

    writing = asyncio.create_task(mutate())
    await entered.wait()
    detaching = asyncio.create_task(manager.detach_connection(room, pid, socket))
    await asyncio.sleep(0)
    assert pid not in room.connections
    proceed.set()
    await asyncio.gather(writing, detaching)
    assert not room.absent and not room.state.players[0].connected
    assert socket.outgoing.empty()
    await manager.release(room, pid, socket)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selection-pending", "selection", "question-pending", "question", "after-success-pending", "after-success-open"])
async def test_restore_absence_preserves_actor_subphase_history_and_utc_deadline(phase):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    manager = manager_for_test(utcnow=lambda: now)
    room, _, _ = await manager.create_room("Host")
    pid, _ = await manager.join_room_locked(room, "Alice", "joueur")
    await manager.join_room_locked(room, "Bob", "joueur")
    candidate = manager.candidate(room)
    candidate.state = engine.add_theme(candidate.state, "Cinema", "presentateur")
    candidate.state = engine.set_player_connected(candidate.state, pid, True)
    candidate.state = engine.start_game(candidate.state, "presentateur")
    if phase != "selection-pending":
        candidate.state = engine.reveal_choice(candidate.state, "presentateur")
    if phase not in ("selection-pending", "selection"):
        candidate.state = engine.select_theme(candidate.state, 0, "joueur", pid)
        if phase != "question-pending":
            candidate.state = engine.start_timer(candidate.state, "presentateur")
        if phase.startswith("after-success"):
            candidate.state = engine.good_answer(candidate.state, "presentateur")
        if phase == "after-success-open":
            candidate.state = engine.reveal_choice(candidate.state, "presentateur")
    await manager.commit_locked(room, candidate, "game:start", liveness=True)
    before = room.saved
    restored = RoomManager(manager.store, utcnow=lambda: now + timedelta(hours=2))
    await restored.start()
    room = restored.get_room(room.code)
    assert all(not p.connected for p in room.state.players)
    assert room.state.turn_status == "active-absent"
    for key in ("phase", "current_player_index", "active_theme_index", "tunnel_sub_phase", "history"):
        assert getattr(room.state, key) == getattr(before.state.to_game(), key)
    assert room.saved.idle_deadline_utc == before.idle_deadline_utc
    assert room.saved.game_id == before.game_id and room.saved.revision == before.revision + 1
    assert await restored.ready()


@pytest.mark.asyncio
async def test_restore_expired_room_archived_before_ready():
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    manager = manager_for_test(utcnow=lambda: now)
    room, _, _ = await manager.create_room("Host")
    deadline = room.saved.idle_deadline_utc
    restored = RoomManager(manager.store, utcnow=lambda: deadline)
    await restored.start()
    assert not restored._rooms
    archived = manager.store.heads[room.saved.room_id]
    assert archived.status == "expired" and archived.idle_deadline_utc == deadline
    assert all(s.status == "revoked" for s in archived.sessions)
    assert await restored.ready()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["check", "load_live", "write"])
async def test_startup_db_schema_or_recovery_failure_never_ready(stage):
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    # Keep durable connected state, but stop this test's delivery worker.
    room.deliveries[socket].task.cancel()
    await asyncio.gather(room.deliveries[socket].task, return_exceptions=True)
    setattr(manager.store, stage, AsyncMock(side_effect=PersistenceUnavailable()))
    restored = RoomManager(manager.store)
    with pytest.raises(PersistenceUnavailable):
        await restored.start()
    assert not await restored.ready()


@pytest.mark.asyncio
async def test_heartbeat_renews_only_liveness_then_reset_retains_archives():
    now = [datetime(2026, 10, 23, tzinfo=timezone.utc)]
    monotonic = [0.0]
    manager = manager_for_test(utcnow=lambda: now[0], clock=lambda: monotonic[0])
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    before = room.saved
    now[0] += timedelta(seconds=60)
    monotonic[0] = 60
    await manager.cleanup_once()
    assert room.saved.state == before.state and room.saved.sessions == before.sessions
    assert room.saved.idle_deadline_utc == before.idle_deadline_utc + timedelta(seconds=60)
    assert len(manager.store.events) == 2
    await manager.commit_locked(room, manager.candidate(room), "game:reset", pid)
    assert room.saved.game_id != before.game_id
    assert len(manager.store.archives) == 4
    await manager.release(room, pid, socket)


def test_private_url_priority_invalid_no_fallback_and_redaction(monkeypatch):
    public = "postgresql://user:public-proof@public.example/game"
    private = "postgresql://user:private-proof@db.railway.internal/game"
    monkeypatch.setenv("DATABASE_URL", public)
    monkeypatch.setenv("DATABASE_PRIVATE_URL", private)
    config = DatabaseConfig.from_environment()
    assert config.url == private and config.tls_mode == "verify-full"
    assert "private-proof" not in repr(config) and "public-proof" not in repr(config)
    monkeypatch.setenv("DATABASE_PRIVATE_URL", "private-proof")
    with pytest.raises(ValueError) as exc:
        DatabaseConfig.from_environment()
    assert str(exc.value) == "Invalid Postgres configuration."
    monkeypatch.delenv("DATABASE_PRIVATE_URL")
    assert DatabaseConfig.from_environment().url == public


def test_private_variable_does_not_authorize_plaintext(monkeypatch):
    monkeypatch.setenv("DATABASE_PRIVATE_URL", "postgresql://user:proof@public.example/game")
    monkeypatch.setenv("DB_TLS_MODE", "private-network")
    with pytest.raises(ValueError, match="Invalid Postgres configuration"):
        DatabaseConfig.from_environment()


def test_production_factory_selects_postgres_without_implicit_migrations(monkeypatch):
    monkeypatch.setenv("DATABASE_PRIVATE_URL", "postgresql://user:proof@db.railway.internal/game")
    store = StrictStore()
    with patch("app.main.PostgresStore", return_value=store) as factory:
        with TestClient(create_app(Settings())) as client:
            assert client.get("/health/ready").status_code == 200
        factory.assert_called_once()


def test_health_liveness_independent_readiness_and_no_store_errors():
    store = StrictStore()
    with TestClient(create_app(Settings(), store=store)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        store.check = AsyncMock(side_effect=PersistenceUnavailable())
        assert client.get("/health").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.headers["Cache-Control"] == "no-store"
        store.write = AsyncMock(side_effect=PersistenceUnavailable())
        response = client.post("/api/rooms", json={"pseudo": "Host"})
        assert response.status_code == 503 and response.headers["Cache-Control"] == "no-store"
        assert response.json()["detail"]["code"] == "persistence_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("event,payload", [
    ("theme:add", {"label": "Cinema"}), ("room:quit", {}),
    ("player:rename", {"name": "Another"}),
])
async def test_ws_known_write_failure_no_candidate_sync_or_terminal(monkeypatch, event, payload):
    manager = manager_for_test()
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(ws, "global_bucket", TokenBucket(10000, 10000))
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    socket.command("session:auth", {"localPlayerId": pid, "sessionToken": token})
    task = asyncio.create_task(ws.websocket_endpoint(socket, room.code))
    await socket.sync()
    before = room.saved
    manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
    socket.command(event, payload)
    error = await asyncio.wait_for(socket.outgoing.get(), 1)
    assert error == {"type": "error", "payload": {
        "code": "persistence_unavailable", "message": "Room persistence unavailable.",
    }}
    assert room.saved == before and not room.closed
    assert room.connections[pid] is socket and socket.outgoing.empty()
    socket.incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})
    await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
async def test_ws_auth_db_failure_returns_transient_error_without_revocation(monkeypatch):
    manager = manager_for_test()
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    room, pid, token = await manager.create_room("Host")
    manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
    socket = Socket()
    socket.command("session:auth", {"localPlayerId": pid, "sessionToken": token})
    await asyncio.wait_for(ws.websocket_endpoint(socket, room.code), 1)
    assert (await socket.outgoing.get())["payload"]["code"] == "persistence_unavailable"
    assert socket.closes[0] == (1013, "persistence_unavailable")
    manager.verify(room, pid, token)
    assert not room.connections and not room.state.players[0].connected


@pytest.mark.asyncio
async def test_rest_join_failure_never_discloses_generated_identity():
    store = StrictStore()
    with TestClient(create_app(Settings(), store=store)) as client:
        identity = client.post("/api/rooms", json={"pseudo": "Host"}).json()
        before = list(store.archives)
        store.write = AsyncMock(side_effect=PersistenceUnavailable())
        response = client.post(f"/api/rooms/{identity['code']}/join", json={"pseudo": "Alice"})
        assert response.status_code == 503
        assert response.headers["Cache-Control"] == "no-store"
        assert set(response.json()) == {"detail"}
        assert store.archives == before


@pytest.mark.asyncio
@pytest.mark.parametrize("correction_fails", [False, True])
async def test_cross_participant_detach_during_attach_reconciles_uninstalled_presence(correction_fails):
    manager = manager_for_test()
    room, a, ta = await manager.create_room("A")
    b, tb = await manager.join_room_locked(room, "B", "joueur")
    sa, sb = Socket(), Socket()
    await attach(manager, room, a, ta, sa)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        if correction_fails and args[2] and args[2].kind == "session:detach":
            raise PersistenceUnavailable()
        if args[2] and args[2].kind == "session:attach":
            entered.set()
            await proceed.wait()
        await original(*args)

    manager.store.write = delayed

    async def attach_b():
        async with room.lock:
            await manager.attach_locked(room, b, tb, sb)

    task = asyncio.create_task(attach_b())
    await entered.wait()
    detached = asyncio.create_task(manager.detach_connection(room, a, sa))
    await asyncio.sleep(0)
    assert room.absent == {a}
    proceed.set()
    with pytest.raises(PersistenceUnavailable):
        await task
    await detached
    assert not room.connections
    if correction_fails:
        assert room.blocked and room.absent == {a, b} and not await manager.ready()
    else:
        assert not room.absent and not room.blocked
        assert all(not p.connected for p in room.saved.state.to_game().players)
        assert await manager.ready()
    assert sb.outgoing.empty()
    await manager.release(room, a, sa)


@pytest.mark.asyncio
async def test_ws_disconnect_frame_removes_authority_during_command_commit(monkeypatch):
    from starlette.websockets import WebSocket
    import json

    manager = manager_for_test()
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    room, pid, token = await manager.create_room("Host")
    frames, sent = asyncio.Queue(), asyncio.Queue()
    socket = WebSocket({"type": "websocket", "path": f"/ws/{room.code}", "query_string": b"",
                        "headers": [(b"origin", b"http://localhost:5173")]}, frames.get, sent.put)

    def command(event, payload):
        frames.put_nowait({"type": "websocket.receive", "text": json.dumps({"type": event, "payload": payload})})

    frames.put_nowait({"type": "websocket.connect"})
    command("session:auth", {"localPlayerId": pid, "sessionToken": token})
    handler = asyncio.create_task(ws.websocket_endpoint(socket, room.code))
    assert (await asyncio.wait_for(sent.get(), 1))["type"] == "websocket.accept"
    assert json.loads((await asyncio.wait_for(sent.get(), 1))["text"])["type"] == "room:state_sync"
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        if args[2] and args[2].kind == "theme:add":
            entered.set()
            await proceed.wait()
        await original(*args)

    manager.store.write = delayed
    command("theme:add", {"label": "Cinema"})
    await entered.wait()
    frames.put_nowait({"type": "websocket.disconnect", "code": 1000})
    for _ in range(20):
        await asyncio.sleep(0)
        if pid not in room.connections:
            break
    assert pid not in room.connections and pid in room.absent
    assert socket not in manager.authenticated_connections and not handler.done()
    assert not await manager.ready()
    proceed.set()
    await asyncio.wait_for(handler, 1)
    assert not room.state.players[0].connected and not room.absent
    assert all(frame["type"] != "websocket.send" for frame in list(sent._queue))


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["success", "cancel", "failure"])
async def test_cross_room_auth_capacity_reserved_before_write(monkeypatch, finish):
    monkeypatch.setattr(settings, "max_authenticated_connections", 1)
    manager = manager_for_test()
    ra, a, ta = await manager.create_room("A")
    rb, b, tb = await manager.create_room("B")
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        entered.set()
        await proceed.wait()
        if finish == "failure":
            raise PersistenceUnavailable()
        await original(*args)

    manager.store.write = delayed
    sa, sb = Socket(), Socket()
    first = asyncio.create_task(manager.attach_locked(ra, a, ta, sa))
    await entered.wait()
    with pytest.raises(CapacityError):
        await manager.attach_locked(rb, b, tb, sb)
    assert manager.auth_reservations == {sa}
    if finish == "cancel":
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    else:
        proceed.set()
        if finish == "failure":
            with pytest.raises(PersistenceUnavailable):
                await first
        else:
            await first
    assert not manager.auth_reservations
    assert len(manager.authenticated_connections) == (finish == "success")
    manager.store.write = original
    if finish == "success":
        await manager.release(ra, a, sa)
    await attach(manager, rb, b, tb, sb)
    await manager.release(rb, b, sb)


@pytest.mark.asyncio
async def test_dephased_heartbeat_renews_each_sweep_and_caps_scheduler(monkeypatch):
    tick = [0.0]
    epoch = datetime(2026, 10, 23, tzinfo=timezone.utc)
    manager = manager_for_test(clock=lambda: tick[0], utcnow=lambda: epoch + timedelta(seconds=tick[0]))
    await manager.cleanup_once()
    tick[0] = 1
    room, pid, token = await manager.create_room("Host")
    socket = Socket()
    await attach(manager, room, pid, token, socket)
    tick[0] = 60
    await manager.cleanup_once()
    assert room.saved.last_liveness_at == epoch + timedelta(seconds=60)
    tick[0] = 120
    await manager.cleanup_once()
    assert room.saved.last_liveness_at == epoch + timedelta(seconds=120)
    monkeypatch.setattr(settings, "room_cleanup_interval_seconds", 300)
    with patch("app.rooms.manager.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await manager.cleanup_loop()
        sleep.assert_awaited_once_with(60)
    manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
    tick[0] = 180
    await manager.cleanup_once()
    assert room.blocked and not await manager.ready()
    await manager.release(room, pid, socket)


@pytest.mark.asyncio
async def test_heartbeat_scheduler_does_not_accumulate_sweep_duration():
    tick = [0.0]
    manager = manager_for_test(clock=lambda: tick[0])
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        if len(sleeps) == 3:
            raise asyncio.CancelledError()
        tick[0] += delay

    async def cleanup():
        tick[0] += 7

    manager.cleanup_once = cleanup
    with patch("app.rooms.manager.asyncio.sleep", sleep):
        with pytest.raises(asyncio.CancelledError):
            await manager.cleanup_loop()
    assert sleeps == [60, 53, 53]


@pytest.mark.asyncio
@pytest.mark.parametrize("end", ["cancel", "timeout", "success"])
async def test_rest_operation_admission_covers_lock_wait_and_releases(monkeypatch, end):
    from app.api import rooms
    from starlette.requests import Request
    from fastapi import HTTPException
    import json

    manager = manager_for_test()
    monkeypatch.setattr(rooms, "room_manager", manager)
    monkeypatch.setattr(rooms, "rest_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(settings, "max_rest_operations", 1)
    monkeypatch.setattr(settings, "rest_operation_timeout_seconds", .03 if end == "timeout" else 1)
    room, pid, token = await manager.create_room("Host")
    deadline = room.saved.idle_deadline_utc

    def request():
        async def receive():
            return {"type": "http.request", "body": json.dumps({"localPlayerId": pid, "sessionToken": token}).encode()}
        return Request({"type": "http"}, receive)

    async def operation():
        gate = rooms.admission()
        await anext(gate)
        try:
            return await rooms.join_room(room.code, request())
        except BaseException as exc:
            await gate.athrow(exc)
            raise
        finally:
            await gate.aclose()

    await room.lock.acquire()
    task = asyncio.create_task(operation())
    await asyncio.sleep(0)
    assert rooms.operations == 1 and rooms.body_readers == 0
    with pytest.raises(HTTPException) as saturated:
        await anext(rooms.admission())
    assert saturated.value.status_code == 503
    if end == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif end == "timeout":
        with pytest.raises(HTTPException) as timeout:
            await task
        assert timeout.value.status_code == 503
    room.lock.release()
    if end == "success":
        assert (await task).status_code == 200
    assert rooms.operations == 0
    assert (await operation()).status_code == 200
    assert room.saved.idle_deadline_utc == deadline


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "attach", "command"])
async def test_matching_complete_commit_confirmation_finishes_without_replay(operation):
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    original = manager.store.write
    writes = []

    async def committed_then_unknown(*args):
        writes.append(args[0].write_id)
        await original(*args)
        raise CommitUnknown()

    manager.store.write = committed_then_unknown
    socket = Socket()
    if operation == "create":
        created, member, proof = await manager.create_room("Other")
        manager.verify(created, member, proof)
        assert manager.get_room(created.code) is created and not manager.pending_creations
    elif operation == "attach":
        await attach(manager, room, pid, token, socket)
        await socket.sync()
        assert room.connections[pid] is socket and not room.blocked
    else:
        candidate = manager.candidate(room)
        candidate.state = engine.add_theme(room.state, "Cinema", "presentateur")
        await manager.commit_locked(room, candidate, "theme:add", pid)
        assert len(room.state.themes) == 1
    assert len(writes) == 1 and await manager.ready()
    manager.store.write = original
    if operation == "attach":
        await manager.release(room, pid, socket)


@pytest.mark.asyncio
async def test_cancelled_attach_with_confirmed_commit_reconciles_absence_without_authority():
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    original = manager.store.write
    entered = asyncio.Event()

    async def committed_cancel(*args):
        await original(*args)
        if args[2].kind == "session:attach":
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise CommitUnknown() from None

    manager.store.write = committed_cancel
    task = asyncio.create_task(manager.attach_locked(room, pid, token, Socket()))
    await entered.wait()
    task.cancel()
    with pytest.raises(PersistenceUnavailable):
        await task
    assert not room.connections and not manager.auth_reservations
    assert not room.state.players[0].connected and not room.absent and not room.blocked
    assert manager.store.events[-1].kind == "session:detach"
    assert await manager.ready()


@pytest.mark.asyncio
async def test_replaced_socket_counts_until_transport_cleanup(monkeypatch):
    manager = manager_for_test()
    room, pid, token = await manager.create_room("Host")
    other, qid, proof = await manager.create_room("Other")
    old, new = Socket(), Socket()
    monkeypatch.setattr(settings, "max_authenticated_connections", 2)
    await attach(manager, room, pid, token, old)
    await attach(manager, room, pid, token, new)
    assert manager.authenticated_connections == {old, new}
    with pytest.raises(CapacityError):
        await manager.attach_locked(other, qid, proof, Socket())
    await manager.release(room, pid, old)
    assert room.connections[pid] is new
    await manager.release(room, pid, new)


@pytest.mark.parametrize("field,value", [("max_rest_operations", 0), ("max_rest_operations", 1.5),
                                         ("rest_operation_timeout_seconds", 0),
                                         ("rest_operation_timeout_seconds", float("inf"))])
def test_rest_operation_settings_are_bounded(field, value):
    config = Settings()
    setattr(config, field, value)
    with pytest.raises(ValueError):
        config.validate()


@pytest.mark.asyncio
async def test_rest_router_admission_is_active_while_valid_request_waits_on_db(monkeypatch):
    from app.api import rooms
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    manager = manager_for_test()
    monkeypatch.setattr(rooms, "room_manager", manager)
    monkeypatch.setattr(rooms, "rest_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(settings, "max_rest_operations", 1)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        entered.set()
        await proceed.wait()
        await original(*args)

    manager.store.write = delayed
    app = FastAPI()
    app.include_router(rooms.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/rooms", json={"pseudo": "Host"}))
        await entered.wait()
        response = await client.post("/api/rooms", json={"pseudo": "Other"})
        assert response.status_code == 503 and response.headers["Cache-Control"] == "no-store"
        assert rooms.operations == 1 and rooms.body_readers == 0
        proceed.set()
        assert (await first).status_code == 200
        assert rooms.operations == 0
        assert (await client.post("/api/rooms", json={"pseudo": "Next"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("correction", ["success", "failure", "cancel", "unknown_confirmed"])
async def test_rest_confirmed_join_keeps_proof_when_other_transport_disappears(monkeypatch, correction):
    from app.api import rooms
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    manager = manager_for_test()
    monkeypatch.setattr(rooms, "room_manager", manager)
    monkeypatch.setattr(rooms, "rest_bucket", TokenBucket(10000, 10000))
    room, a, ta = await manager.create_room("A")
    c, tc = await manager.join_room_locked(room, "C", "joueur")
    sa, sc = Socket(), Socket()
    await attach(manager, room, a, ta, sa)
    await attach(manager, room, c, tc, sc)
    await sc.sync()
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        kind = args[2].kind if args[2] else None
        if kind == "room:join":
            entered.set()
            await proceed.wait()
        if kind == "session:detach":
            if correction == "failure":
                raise PersistenceUnavailable()
            if correction == "cancel":
                raise asyncio.CancelledError()
        await original(*args)
        if kind == "room:join" and correction == "unknown_confirmed":
            raise CommitUnknown()

    manager.store.write = delayed
    app = FastAPI()
    app.include_router(rooms.router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request = asyncio.create_task(client.post(f"/api/rooms/{room.code}/join", json={"pseudo": "B"}))
            await entered.wait()
            manager.lose_connection(room, a, sa)  # cleanup deliberately delayed
            proceed.set()
            response = await asyncio.wait_for(request, 1)
            assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
            body = response.json()
            b, tb = body["localPlayerId"], body["sessionToken"]
            manager.verify(room, b, tb)
            assert len(room.roles) == 3 and sum(e.kind == "room:join" for e in manager.store.events) == 2
            failed = correction in ("failure", "cancel")
            assert room.blocked == failed
            if failed:
                assert body["state"] is None and body["persistenceUnavailable"] is True
                assert sc.outgoing.empty()
                with pytest.raises(PersistenceUnavailable):
                    await manager.attach_locked(room, b, tb, Socket())
                assert (await client.post(f"/api/rooms/{room.code}/join", json={
                    "localPlayerId": b, "sessionToken": tb})).status_code == 503
            else:
                assert not room.absent and body["state"]["players"][0]["connected"] is False
                assert (await sc.sync())["players"][0]["connected"] is False
                # Retry is proof-based resume, never another membership write.
                assert (await client.post(f"/api/rooms/{room.code}/join", json={
                    "localPlayerId": b, "sessionToken": tb})).status_code == 200
                sb = Socket()
                await attach(manager, room, b, tb, sb)
                await manager.release(room, b, sb)
            assert len(room.roles) == 3
    finally:
        proceed.set()
        manager.store.write = original
        await manager.release(room, a, sa)
        await manager.release(room, c, sc)


@pytest.mark.asyncio
async def test_attach_reconciliation_publishes_to_third_recipient_without_disconnect_cleanup():
    manager = manager_for_test()
    room, _, _ = await manager.create_room("Host")
    a, ta = await manager.join_room_locked(room, "A", "joueur")
    b, tb = await manager.join_room_locked(room, "B", "joueur")
    c, tc = await manager.join_room_locked(room, "C", "joueur")
    sa, sb, sc = Socket(), Socket(), Socket()
    await attach(manager, room, a, ta, sa)
    await attach(manager, room, c, tc, sc)
    await sc.sync()
    async with room.lock:
        candidate = manager.candidate(room)
        candidate.state = engine.add_theme(candidate.state, "Cinema", "presentateur")
        candidate.state = engine.start_game(candidate.state, "presentateur", rng=random.Random(1))
        await manager.commit_locked(room, candidate, "game:start", a)
        manager.publish_locked(room)
    await sc.sync()
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        if args[2] and args[2].kind == "session:attach":
            entered.set()
            await proceed.wait()
        await original(*args)

    async def attaching():
        async with room.lock:
            await manager.attach_locked(room, b, tb, sb)

    manager.store.write = delayed
    task = asyncio.create_task(attaching())
    try:
        await entered.wait()
        manager.lose_connection(room, a, sa)
        proceed.set()
        with pytest.raises(PersistenceUnavailable):
            await task
        state = await asyncio.wait_for(sc.sync(), 1)
        assert state["turnStatus"] == "active-absent"
        assert [p["connected"] for p in state["players"]] == [False, False, False, True]
        assert not room.absent and not room.blocked and sb.outgoing.empty()
        await manager.release(room, a, sa)
        assert sc.outgoing.empty()
    finally:
        proceed.set()
        manager.store.write = original
        await manager.release(room, a, sa)
        await manager.release(room, c, sc)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["auth", "command"])
@pytest.mark.parametrize("end", ["overflow", "disconnect"])
@pytest.mark.parametrize("correction", ["success", "failure", "cancel", "unknown_confirmed"])
async def test_ws_transport_cause_survives_paused_commit(monkeypatch, stage, end, correction):
    from starlette.websockets import WebSocket
    import json

    manager = manager_for_test()
    close_attempts = []
    original_close = manager.close_socket

    async def close_socket(socket, code, reason=""):
        close_attempts.append(code)
        await original_close(socket, code, reason)

    monkeypatch.setattr(manager, "close_socket", close_socket)
    monkeypatch.setattr(ws, "room_manager", manager)
    monkeypatch.setattr(ws, "upgrade_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(settings, "ws_command_rate_burst", 2)
    room, pid, token = await manager.create_room("Host")
    frames, sent = asyncio.Queue(), asyncio.Queue()
    socket = WebSocket({"type": "websocket", "path": f"/ws/{room.code}", "query_string": b"",
                        "headers": [(b"origin", b"http://localhost:5173")]}, frames.get, sent.put)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = manager.store.write

    async def delayed(*args):
        if args[2] and args[2].kind == ("session:attach" if stage == "auth" else "theme:add"):
            entered.set()
            await proceed.wait()
        if args[2] and args[2].kind == "session:detach":
            if correction == "failure":
                raise PersistenceUnavailable()
            if correction == "cancel":
                raise asyncio.CancelledError()
        await original(*args)
        if args[2] and args[2].kind == "session:detach" and correction == "unknown_confirmed":
            raise CommitUnknown()

    def command(kind, payload):
        frames.put_nowait({"type": "websocket.receive", "text": json.dumps({"type": kind, "payload": payload})})

    manager.store.write = delayed
    frames.put_nowait({"type": "websocket.connect"})
    command("session:auth", {"localPlayerId": pid, "sessionToken": token})
    handler = asyncio.create_task(ws.websocket_endpoint(socket, room.code))
    try:
        assert (await asyncio.wait_for(sent.get(), 1))["type"] == "websocket.accept"
        if stage == "command":
            assert json.loads((await asyncio.wait_for(sent.get(), 1))["text"])["type"] == "room:state_sync"
            command("theme:add", {"label": "Cinema"})
        await entered.wait()
        if end == "overflow":
            for _ in range(3):
                command("theme:add", {"label": "Must not replay"})
        else:
            frames.put_nowait({"type": "websocket.disconnect", "code": 1000})
        for _ in range(30):
            await asyncio.sleep(0)
            if socket in manager.lost_transports:
                break
        assert socket in manager.lost_transports and pid not in room.connections
        proceed.set()
        outcome = (await asyncio.wait_for(asyncio.gather(handler, return_exceptions=True), 1))[0]
        assert outcome is None or (correction == "cancel" and isinstance(outcome, asyncio.CancelledError))
        output = list(sent._queue)
        errors = [json.loads(f["text"]) for f in output if f["type"] == "websocket.send"]
        closes = [f["code"] for f in output if f["type"] == "websocket.close"]
        if end == "overflow":
            assert errors == [{"type": "error", "payload": {"code": "rate_limited", "message": "Rate limited."}}]
            assert closes == [4429]
        else:
            assert errors == [] and closes == [] and close_attempts == []
        failed = correction in ("failure", "cancel")
        assert bool(room.absent) == failed and room.blocked == failed
        assert room.state.players[0].connected == failed
        assert sum(e.kind == "session:attach" for e in manager.store.events) == 1
        assert sum(e.kind == "theme:add" for e in manager.store.events) == (1 if stage == "command" else 0)
        assert len(room.state.themes) == (1 if stage == "command" else 0)
        assert not manager.auth_reservations and not manager.authenticated_connections and not room.deliveries
    finally:
        proceed.set()
        if not handler.done():
            handler.cancel()
        await asyncio.gather(handler, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_queued_snapshot_discarded_when_presence_becomes_unavailable(blocked):
    manager = manager_for_test()
    room, a, ta = await manager.create_room("A")
    c, tc = await manager.join_room_locked(room, "C", "joueur")
    sa, sc = Socket(), Socket()
    await attach(manager, room, a, ta, sa)
    await attach(manager, room, c, tc, sc)
    await sc.sync()
    original = manager.store.write
    try:
        async with room.lock:
            manager.publish_locked(room)
            assert room.deliveries[sc].pending["payload"]["state"]["players"][0]["connected"]
            manager.lose_connection(room, a, sa)
            if blocked:
                manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
                with pytest.raises(PersistenceUnavailable):
                    await manager.reconcile_presence_locked(room)
        for _ in range(10):
            await asyncio.sleep(0)
        assert sc.outgoing.empty()
        assert room.deliveries[sc].pending is None and not room.deliveries[sc].wake.is_set()
        manager.store.write = original
        # A later bounded reconciliation is the only source of a fresh sync.
        room.blocked = False
        async with room.lock:
            await manager.reconcile_presence_locked(room)
        assert (await sc.sync())["players"][0]["connected"] is False
        assert sc.outgoing.empty()
    finally:
        manager.store.write = original
        await manager.release(room, a, sa)
        await manager.release(room, c, sc)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "error", "cancel", "timeout"])
async def test_readiness_admission_is_immediate_single_slot_and_releases(monkeypatch, outcome):
    from app import main
    from httpx import ASGITransport, AsyncClient

    manager = manager_for_test()
    monkeypatch.setattr(main, "manager", manager)
    entered, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def check():
        nonlocal calls
        calls += 1
        entered.set()
        await proceed.wait()
        if outcome == "error":
            raise PersistenceUnavailable()

    manager.store.check = check
    async with AsyncClient(transport=ASGITransport(app=main.create_app()), base_url="http://test") as client:
        first = asyncio.create_task(client.get("/health/ready"))
        await entered.wait()
        others = await asyncio.wait_for(asyncio.gather(*(client.get("/health/ready") for _ in range(32))), 1)
        assert calls == 1 and manager.readiness_checking
        assert all(r.status_code == 503 and r.headers["cache-control"] == "no-store" for r in others)
        if outcome == "cancel":
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        else:
            if outcome != "timeout":
                proceed.set()
            response = await asyncio.wait_for(first, 3)
            assert response.status_code == (200 if outcome == "success" else 503)
            assert response.headers["cache-control"] == "no-store"
        assert not manager.readiness_checking
        manager.store.check = AsyncMock()
        assert (await client.get("/health/ready")).status_code == 200
        room, _, _ = await manager.create_room("Host")
        room.blocked = True
        manager.store.check.reset_mock()
        assert (await client.get("/health/ready")).status_code == 503
        manager.store.check.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["failed_presence", "replacement"])
async def test_extracted_snapshot_revalidated_after_waiting_for_error_send(interruption):
    class ErrorBlockedSocket(Socket):
        async def send_json(self, message):
            if message["type"] == "error":
                error_started.set()
                await error_proceed.wait()
            await super().send_json(message)

    class ObservedLock(asyncio.Lock):
        async def acquire(self):
            if self.locked():
                snapshot_waiting.set()
            return await super().acquire()

    manager = manager_for_test()
    room, a, ta = await manager.create_room("A")
    c, tc = await manager.join_room_locked(room, "C", "joueur")
    sa, sc, replacement = Socket(), ErrorBlockedSocket(), Socket()
    error_started, error_proceed, snapshot_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = manager.store.write
    error_send = None
    try:
        await attach(manager, room, a, ta, sa)
        await attach(manager, room, c, tc, sc)
        await sc.sync()
        sc.lock = replacement.lock = room.lock
        delivery = room.deliveries[sc]
        delivery.acknowledged.clear()
        delivery.send_lock = ObservedLock()
        error = {"type": "error", "payload": {"code": "invalid_payload", "message": "Invalid message."}}
        error_send = asyncio.create_task(manager.send(room, sc, error))
        await asyncio.wait_for(error_started.wait(), 1)
        async with room.lock:
            manager.publish_locked(room)
        await asyncio.wait_for(snapshot_waiting.wait(), 1)
        assert delivery.pending is None  # Extracted, not merely queued.
        if interruption == "failed_presence":
            manager.lose_connection(room, a, sa)
            manager.store.write = AsyncMock(side_effect=PersistenceUnavailable())
            async with room.lock:
                with pytest.raises(PersistenceUnavailable):
                    await manager.reconcile_presence_locked(room)
            assert room.blocked and room.absent == {a}
        else:
            await attach(manager, room, c, tc, replacement)
            await replacement.sync()
            assert room.connections[c] is replacement
        error_proceed.set()
        await asyncio.wait_for(error_send, 1)
        assert await asyncio.wait_for(sc.outgoing.get(), 1) == error
        for _ in range(10):
            await asyncio.sleep(0)
        assert sc.outgoing.empty()
        if interruption == "failed_presence":
            assert not delivery.acknowledged.is_set()
            manager.store.write = original
            # Explicit bounded reconciliation, not an automatic command replay.
            room.blocked = False
            async with room.lock:
                await manager.reconcile_presence_locked(room)
            assert (await sc.sync())["players"][0]["connected"] is False
            assert sc.outgoing.empty()
        else:
            await manager.release(room, c, sc)
            assert room.connections[c] is replacement and room.state.players[1].connected
            assert not room.absent and not room.blocked
    finally:
        error_proceed.set()
        manager.store.write = original
        if error_send is not None:
            await asyncio.gather(error_send, return_exceptions=True)
        await manager.release(room, a, sa)
        await manager.release(room, c, sc)
        await manager.release(room, c, replacement)
