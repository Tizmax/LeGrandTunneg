"""Offline contracts, never evidence of a real Postgres transaction."""

import asyncio
import json
import runpy
import ssl
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.game import engine
from app.game.types import GameState
from app.persistence.codec import InvalidSnapshot, SavedGame, SavedSession, SavedTheme, Snapshot, decode, encode
from app.persistence.config import DatabaseConfig
from app.persistence.store import CommitUnknown, Event, PersistenceUnavailable, PostgresStore, RevisionConflict


@pytest.fixture
def candidate():
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    pid = uuid4()
    state = engine.add_player(GameState(), str(pid), "Paul", is_presenter=True)
    return Snapshot(
        format_version=1, room_id=uuid4(), game_id=uuid4(), write_id=uuid4(),
        code="ABCD", revision=1, status="live", created_at=now, closed_at=None,
        idle_deadline_utc=now + timedelta(days=1), last_liveness_at=now,
        presenter_id=pid, state=SavedGame.from_game(state),
        sessions=(SavedSession(participant_id=pid, name="Paul", role="presentateur",
                               proof_digest="ab" * 32, status="active", created_at=now, revoked_at=None),),
    )


def test_private_roundtrip_no_runtime_or_public_projection(candidate):
    assert decode(encode(candidate)) == candidate
    assert decode(encode(candidate)).state.to_game() == candidate.state.to_game()
    payload = json.loads(encode(candidate))
    assert payload["sessions"][0]["proof_digest"] == "ab" * 32
    assert not {"connections", "deliveries", "lock", "idle_since", "sessionToken"} & payload.keys()
    with pytest.raises(InvalidSnapshot):
        encode(SimpleNamespace(state=candidate.state))
    with pytest.raises(ValidationError):
        candidate.revision = 2


def test_format_is_independent_of_configurable_admission_limits(candidate):
    payload = json.loads(encode(candidate))
    payload["state"]["players"][0]["name"] = "P" * 25
    payload["sessions"][0]["name"] = "P" * 25
    payload["state"]["themes"] = [
        {"label": "T" * 101, "progress_value": 0, "validated_squares": 0,
         "completed": False, "discovered": False, "nullified": []}
    ] * 33
    assert len(decode(json.dumps(payload)).state.themes) == 33


@pytest.mark.parametrize("change", [
    {"format_version": 2}, {"format_version": True}, {"revision": True},
    {"revision": "1"}, {"lock": {}}, {"status": "unknown"}, {"presenter_id": str(uuid4())},
    {"idle_deadline_utc": "2026-10-20T00:00:00Z"}, {"created_at": "2026-10-21T00:00:00"},
])
def test_reject_malformed_envelope(candidate, change):
    payload = json.loads(encode(candidate))
    payload.update(change)
    with pytest.raises(InvalidSnapshot, match="Invalid or unsupported private snapshot"):
        decode(json.dumps(payload))


@pytest.mark.parametrize("payload", ["null", "[]", "{", '{"format_version":1,"format_version":1}'])
def test_reject_bad_json(payload):
    with pytest.raises(InvalidSnapshot):
        decode(payload)


@pytest.mark.parametrize("field,value", [
    ("proof_digest", "raw-secret"), ("status", "revoked"), ("role", "joueur"),
    ("participant_id", str(uuid4())), ("sessionToken", "A" * 43),
])
def test_reject_session_inconsistency(candidate, field, value):
    payload = json.loads(encode(candidate))
    payload["sessions"][0][field] = value
    with pytest.raises(InvalidSnapshot):
        decode(json.dumps(payload))


@pytest.mark.parametrize("phase,subphase", [
    ("selection-pending", None), ("selection", None),
    ("tunnel", "question-pending"), ("tunnel", "question"),
    ("tunnel", "after-success-pending"), ("tunnel", "after-success-open"),
])
def test_exact_subphase_and_absent_roundtrip(candidate, phase, subphase):
    state = candidate.state.to_game()
    pid = str(uuid4())
    state = engine.add_player(state, pid, "Alice")
    state = engine.add_theme(state, "Cinema", "presentateur")
    from dataclasses import replace
    state = replace(state, phase=phase, tunnel_sub_phase=subphase,
                    active_theme_index=0 if subphase else None,
                    current_player_index=1, turn_status="active-absent")
    game = SavedGame.from_game(state)
    assert game.to_game() == state
    assert SavedGame.model_validate_json(game.model_dump_json()) == game


@pytest.mark.parametrize("url", ["", "sqlite:///test", "postgresql://", "https://user:secret@host/db", "postgresql://user:secret@host/db?echo=true"])
def test_postgres_url_required_and_redacted(url):
    with pytest.raises(ValueError) as error:
        DatabaseConfig(url)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("key,value", [("pool_size", 0), ("pool_size", True), ("max_overflow", -1),
                                       ("transaction_timeout", float("inf")), ("reconcile_timeout", 0)])
def test_bounded_config(key, value):
    with pytest.raises(ValueError):
        DatabaseConfig("postgresql://user:secret@future.invalid/db", **{key: value})


@pytest.mark.parametrize("budget", [0, -1, True, float("inf"), 10.01])
def test_cleanup_budget_is_bounded(budget):
    with pytest.raises(ValueError):
        DatabaseConfig("postgresql://user:secret@future.invalid/db", cleanup_timeout=budget)


@pytest.mark.parametrize("host,mode,accepted", [
    ("public.example", "verify-full", True),
    ("postgres.railway.internal", "verify-full", True),
    ("postgres.railway.internal", "private-network", True),
    ("POSTGRES.railway.internal", "private-network", True),
    ("public.example", "private-network", False),
    ("railway.internal", "private-network", False),
    ("postgres.railway.internal.evil.example", "private-network", False),
    ("127.0.0.1", "private-network", False),
    ("localhost", "private-network", False),
    ("bad_host.railway.internal", "private-network", False),
    ("-bad.railway.internal", "private-network", False),
    ("postgres.railway.internal", "prefer", False),
    ("postgres.railway.internal", "disable", False),
])
def test_explicit_tls_policy(host, mode, accepted):
    if not accepted:
        with pytest.raises(ValueError) as error:
            DatabaseConfig(f"postgresql://user:secret@{host}/db", tls_mode=mode)
        assert "secret" not in str(error.value)
        return
    config = DatabaseConfig(f"postgresql://user:secret@{host}/db", tls_mode=mode)
    with patch("app.persistence.store.create_async_engine") as create:
        PostgresStore(config)
    args = create.call_args.kwargs["connect_args"]
    if mode == "private-network":
        assert args["ssl"] is False
    else:
        context = args["ssl"]
        assert isinstance(context, ssl.SSLContext)
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.get_ca_certs()


def test_tls_defaults_and_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@postgres.railway.internal/db")
    monkeypatch.delenv("DB_TLS_MODE", raising=False)
    assert DatabaseConfig.from_environment().tls_mode == "verify-full"
    monkeypatch.setenv("DB_TLS_MODE", "private-network")
    monkeypatch.setenv("DB_CLEANUP_TIMEOUT_SECONDS", "0.25")
    config = DatabaseConfig.from_environment()
    assert config.connect_args()["ssl"] is False
    assert config.cleanup_timeout == 0.25
    monkeypatch.setenv("DB_TLS_MODE", "secret-bad-mode")
    with pytest.raises(ValueError, match="^Invalid Postgres configuration\\.$"):
        DatabaseConfig.from_environment()


@pytest.mark.parametrize("mode", ["verify-full", "private-network"])
def test_alembic_online_uses_store_tls_without_contact(monkeypatch, mode):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@postgres.railway.internal/db")
    monkeypatch.setenv("DB_TLS_MODE", mode)
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    connection.sync_connection = MagicMock()
    engine_double = MagicMock()
    engine_double.connect.return_value = connection
    engine_double.dispose = AsyncMock()
    with patch("alembic.context.is_offline_mode", return_value=False), patch(
        "app.persistence.store.create_async_engine", return_value=engine_double
    ) as create:
        runpy.run_path("migrations/env.py")
    tls = create.call_args.kwargs["connect_args"]["ssl"]
    assert tls is False if mode == "private-network" else (
        isinstance(tls, ssl.SSLContext) and tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED)
    connection.run_sync.assert_awaited_once()
    connection.close.assert_awaited_once()
    engine_double.dispose.assert_awaited_once()


@pytest.mark.parametrize("progress,validated,completed", [
    (10, 0, False), (10, 9, False), (10, 0, True), (10, 10, False), (9, 9, True),
])
def test_reject_inconsistent_case_ten(progress, validated, completed):
    with pytest.raises(ValidationError):
        SavedTheme(label="Cinema", progress_value=progress, validated_squares=validated,
                   completed=completed, discovered=False, nullified=())


@pytest.mark.parametrize("subphase", ["question-pending", "question", "after-success-pending", "after-success-open"])
def test_reject_completed_active_tunnel(candidate, subphase):
    state = candidate.state.to_game()
    state = engine.add_player(state, str(uuid4()), "Alice")
    state = engine.set_player_connected(state, state.players[1].id, True)
    state = engine.add_theme(state, "Cinema", "presentateur")
    state = replace(state, phase="tunnel", active_theme_index=0, current_player_index=1,
                    turn_status="ready", tunnel_sub_phase=subphase)
    payload = SavedGame.from_game(state).model_dump(mode="json")
    payload["themes"][0].update(progress_value=10, validated_squares=10, completed=True)
    with pytest.raises(ValidationError):
        SavedGame.model_validate_json(json.dumps(payload))


def test_engine_progress_unvaulted_and_completion_roundtrips(candidate):
    state = candidate.state.to_game()
    state = engine.add_player(state, str(uuid4()), "Alice")
    state = engine.add_player(state, str(uuid4()), "Bob")
    for player in state.players:
        state = engine.set_player_connected(state, player.id, True)
    state = engine.add_theme(state, "Cinema", "presentateur")
    state = engine.start_game(state, "presentateur")
    state = engine.reveal_choice(state, "presentateur")
    actor = state.players[state.current_player_index].id
    state = engine.select_theme(state, 0, "joueur", actor)
    for step in range(1, 11):
        state = engine.start_timer(state, "presentateur")
        state = engine.good_answer(state, "presentateur")
        assert state.themes[0].progress_value == step
        assert state.themes[0].validated_squares == (10 if step == 10 else 0)
        saved = SavedGame.from_game(state)
        assert SavedGame.model_validate_json(saved.model_dump_json()).to_game() == state
        if step < 10:
            state = engine.reveal_choice(state, "presentateur")
            state = engine.continue_tunnel(state, "joueur", actor)
    assert state.themes[0].completed
    assert state.active_theme_index is None


@pytest.fixture
def mock_store():
    config = DatabaseConfig("postgresql://user:secret@future.invalid/db")
    store = PostgresStore(config)
    connection = AsyncMock()
    connection.sync_connection = MagicMock()
    transaction = AsyncMock()
    connection.begin = AsyncMock(return_value=transaction)
    store._engine = MagicMock()
    connection.__aenter__.return_value = connection
    store._engine.connect.return_value = connection
    return store, connection, transaction


@pytest.mark.asyncio
async def test_single_creation_transaction_and_hash_only(candidate, mock_store):
    store, connection, transaction = mock_store
    assert "secret" not in repr(store.config)
    await store.write(candidate, 0, Event("room:create", candidate.created_at))
    assert connection.execute.await_count == 4
    transaction.commit.assert_awaited_once()
    transaction.rollback.assert_not_awaited()
    statement, records = connection.execute.await_args_list[2].args
    assert records[0]["proof_digest"] == bytes.fromhex("ab" * 32)
    assert len(records[0]["proof_digest"]) == 32
    assert "sessionToken" not in str(records)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", [0, 1, 2, 3])
async def test_failure_at_each_statement_rolls_back_no_commit(candidate, mock_store, failure_at):
    store, connection, transaction = mock_store
    connection.execute.side_effect = [None] * failure_at + [OSError("secret URL")]
    with pytest.raises(PersistenceUnavailable) as error:
        await store.write(candidate, 0, Event("room:create", candidate.created_at))
    assert "secret" not in str(error.value)
    transaction.commit.assert_not_awaited()
    transaction.rollback.assert_awaited_once()
    assert candidate.revision == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError("secret"), asyncio.CancelledError(), TimeoutError()])
async def test_commit_failure_unknown_no_retry(candidate, mock_store, failure):
    store, connection, transaction = mock_store
    transaction.commit.side_effect = failure
    with pytest.raises(CommitUnknown, match="Room persistence unavailable"):
        await store.write(candidate, 0, Event("room:create", candidate.created_at))
    transaction.commit.assert_awaited_once()
    transaction.rollback.assert_not_awaited()
    assert connection.execute.await_count == 4


@pytest.mark.asyncio
async def test_occ_conflict_no_snapshot_no_retry(candidate, mock_store):
    store, connection, transaction = mock_store
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = {"revision": 9}
    connection.execute.return_value = result
    next_candidate = candidate.model_copy(update={"revision": 2, "write_id": uuid4()})
    with pytest.raises(RevisionConflict):
        await store.write(next_candidate, 1, Event("theme:add", candidate.created_at))
    assert connection.execute.await_count == 1
    transaction.rollback.assert_awaited_once()
    transaction.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_write_locks_occ_updates_and_commits_once(candidate, mock_store):
    store, connection, transaction = mock_store
    result = MagicMock(rowcount=1)
    result.mappings.return_value.one_or_none.return_value = {"revision": 1}
    connection.execute.return_value = result
    store._read = AsyncMock(return_value=candidate)
    updated = candidate.model_copy(update={"revision": 2, "write_id": uuid4()})
    await store.write(updated, 1, Event("theme:add", candidate.created_at))
    assert connection.execute.await_count == 5
    assert connection.execute.await_args_list[0].args[0]._for_update_arg.nowait
    transaction.commit.assert_awaited_once()
    transaction.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_before_commit_rolls_back_and_propagates(candidate, mock_store):
    store, connection, transaction = mock_store
    connection.execute.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await store.write(candidate, 0, Event("room:create", candidate.created_at))
    transaction.rollback.assert_awaited_once()
    transaction.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("block_at", ["execute", "rollback", "release", "commit"])
async def test_write_timeout_plus_cleanup_budget(candidate, mock_store, block_at):
    store, connection, transaction = mock_store
    store.config = replace(store.config, transaction_timeout=0.02, cleanup_timeout=0.02)
    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()
    if block_at == "execute":
        connection.execute.side_effect = stalled
    elif block_at == "rollback":
        connection.execute.side_effect = OSError("secret")
        transaction.rollback.side_effect = stalled
    elif block_at == "release":
        connection.close.side_effect = stalled
    else:
        transaction.commit.side_effect = stalled
    before = time.monotonic()
    error_type = CommitUnknown if block_at in ("commit", "release") else PersistenceUnavailable
    with pytest.raises(error_type) as error:
        await asyncio.wait_for(store.write(candidate, 0, Event("room:create", candidate.created_at)), 0.5)
    assert time.monotonic() - before < 0.3
    assert "secret" not in str(error.value)
    assert transaction.commit.await_count == (1 if block_at in ("release", "commit") else 0)
    if block_at != "execute":
        connection.sync_connection.connection.detach.assert_called_once()
        connection.sync_connection.connection.driver_connection.terminate.assert_called_once()
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("block_at", ["execute", "rollback", "release", "commit"])
async def test_external_repeated_cancel_cleanup_bounded(candidate, mock_store, block_at):
    store, connection, transaction = mock_store
    store.config = replace(store.config, transaction_timeout=0.2, cleanup_timeout=0.03)
    entered = asyncio.Event()
    async def stalled(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    if block_at == "execute":
        connection.execute.side_effect = stalled
        transaction.rollback.side_effect = stalled
    elif block_at == "rollback":
        connection.execute.side_effect = OSError("secret")
        transaction.rollback.side_effect = stalled
    elif block_at == "release":
        connection.close.side_effect = stalled
    else:
        transaction.commit.side_effect = stalled
    task = asyncio.create_task(store.write(candidate, 0, Event("room:create", candidate.created_at)))
    await asyncio.wait_for(entered.wait(), 0.3)
    task.cancel()
    await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(CommitUnknown if block_at in ("release", "commit") else asyncio.CancelledError):
        await asyncio.wait_for(task, 0.3)
    connection.sync_connection.connection.detach.assert_called_once()
    connection.sync_connection.connection.driver_connection.terminate.assert_called_once()
    assert transaction.commit.await_count == (1 if block_at in ("release", "commit") else 0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["rollback", "close"])
async def test_cleanup_failure_terminates_and_hides_secrets(candidate, mock_store, failure_at):
    store, connection, transaction = mock_store
    connection.execute.side_effect = OSError("secret statement")
    if failure_at == "rollback":
        transaction.rollback.side_effect = OSError("secret rollback")
    else:
        connection.close.side_effect = OSError("secret close")
    with pytest.raises(PersistenceUnavailable) as error:
        await store.write(candidate, 0, Event("room:create", candidate.created_at))
    assert type(error.value) is PersistenceUnavailable
    assert str(error.value) == "Room persistence unavailable."
    transaction.commit.assert_not_awaited()
    connection.sync_connection.connection.detach.assert_called_once()
    connection.sync_connection.connection.driver_connection.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_does_not_wait_for_cancellation_resistant_release(candidate, mock_store):
    store, connection, transaction = mock_store
    store.config = replace(store.config, cleanup_timeout=0.02)
    finished = asyncio.Event()
    escaped = asyncio.Event()
    async def resistant():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            escaped.set()
            await finished.wait()
    connection.close.side_effect = resistant
    try:
        with pytest.raises(CommitUnknown):
            await asyncio.wait_for(store.write(candidate, 0, Event("room:create", candidate.created_at)), 0.3)
        await asyncio.wait_for(escaped.wait(), 0.3)
        connection.sync_connection.connection.detach.assert_called_once()
        connection.sync_connection.connection.driver_connection.terminate.assert_called_once()
        transaction.commit.assert_awaited_once()
    finally:
        finished.set()
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["check", "load_live", "reconcile"])
async def test_read_context_release_is_bounded(candidate, mock_store, operation):
    store, connection, _ = mock_store
    store.config = replace(store.config, cleanup_timeout=0.02)
    async def stalled():
        await asyncio.Event().wait()
    connection.close.side_effect = stalled
    result = MagicMock()
    result.scalars.return_value.all.return_value = ["0001_private_snapshots"]
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.one_or_none.return_value = None
    connection.execute.return_value = result
    if operation == "reconcile":
        assert await asyncio.wait_for(store.reconcile(candidate, 0), 0.3) == "blocked"
    else:
        with pytest.raises(PersistenceUnavailable):
            await asyncio.wait_for(getattr(store, operation)(), 0.3)
    connection.sync_connection.connection.detach.assert_called_once()
    connection.sync_connection.connection.driver_connection.terminate.assert_called_once()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_read_crosschecks_snapshot_and_session_authority(candidate, mock_store):
    store, connection, _ = mock_store
    row = {key: getattr(candidate, key) for key in (
        "room_id", "code", "status", "game_id", "revision", "write_id", "created_at",
        "closed_at", "idle_deadline_utc", "last_liveness_at")}
    saved = MagicMock()
    saved.mappings.return_value.one.return_value = {
        "format_version": 1, "game_id": candidate.game_id, "write_id": candidate.write_id,
        "payload": json.loads(encode(candidate)),
    }
    proof = candidate.sessions[0]
    session_result = MagicMock()
    record = {"participant_id": proof.participant_id, "proof_digest": bytes.fromhex(proof.proof_digest),
              "role": proof.role, "status": proof.status, "created_at": proof.created_at, "revoked_at": None}
    session_result.mappings.return_value.all.return_value = [record]
    connection.execute.side_effect = [saved, session_result]
    assert await store._read(connection, row) == candidate
    record["proof_digest"] = b"wrong"
    connection.execute.side_effect = [saved, session_result]
    with pytest.raises(InvalidSnapshot):
        await store._read(connection, row)
    connection.execute.side_effect = [saved]
    with pytest.raises(InvalidSnapshot):
        await store._read(connection, {**row, "revision": 2})


@pytest.mark.asyncio
async def test_restore_corruption_fails_entire_load(candidate, mock_store):
    store, connection, transaction = mock_store
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"revision": 1}, {"revision": 2}]
    connection.execute.return_value = result
    store._read = AsyncMock(side_effect=[candidate, InvalidSnapshot()])
    with pytest.raises(PersistenceUnavailable):
        await store.load_live()


@pytest.mark.asyncio
async def test_reconciliation_deadline_returns_blocked(candidate, mock_store):
    store, connection, transaction = mock_store
    store.config = DatabaseConfig("postgresql://user:secret@future.invalid/db", reconcile_timeout=0.01)
    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()
    connection.execute.side_effect = stalled
    assert await store.reconcile(candidate, 0) == "blocked"
    assert connection.execute.await_count == 1


def test_revoked_proofs_never_reactivated_or_forgotten(candidate):
    old = candidate.sessions[0].model_copy(update={"status": "revoked", "revoked_at": candidate.created_at})
    previous = candidate.model_copy(update={"sessions": (old,)})
    next_candidate = candidate.model_copy(update={"write_id": uuid4(), "revision": 2})
    with pytest.raises(InvalidSnapshot):
        PostgresStore._validate_transition(previous, next_candidate, Event("room:join", candidate.created_at))


def test_game_identity_change_only_reset_and_heartbeat_is_liveness_only(candidate):
    changed = candidate.model_copy(update={"write_id": uuid4(), "revision": 2, "game_id": uuid4()})
    with pytest.raises(InvalidSnapshot):
        PostgresStore._validate_transition(candidate, changed, Event("theme:add", candidate.created_at))
    PostgresStore._validate_transition(candidate, changed, Event("game:reset", candidate.created_at))
    with pytest.raises(InvalidSnapshot):
        PostgresStore._validate_transition(candidate, changed, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["committed", "not_committed", "divergent", "missing", "error"])
async def test_reconciliation_one_readback_never_replays(candidate, mock_store, outcome):
    store, connection, transaction = mock_store
    transaction.__aenter__.return_value = transaction
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = None if outcome == "missing" else {"revision": 1}
    connection.execute.return_value = result
    if outcome == "error":
        connection.execute.side_effect = OSError("secret")
    saved = candidate
    if outcome == "not_committed":
        saved = candidate.model_copy(update={"revision": 1, "write_id": uuid4()})
        candidate = candidate.model_copy(update={"revision": 2})
    elif outcome == "divergent":
        saved = candidate.model_copy(update={"revision": 8, "write_id": uuid4()})
    store._read = AsyncMock(return_value=saved)
    actual = await store.reconcile(candidate, 1)
    assert actual == (outcome if outcome in ("committed", "not_committed") else "blocked")
    assert connection.execute.await_count == 1
    transaction.commit.assert_not_awaited()
