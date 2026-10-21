"""Bounded Postgres repository. Installation/publishing belong to its caller.

An unknown write must block the caller's room (or pending creation code). No
method retries a command. An absent creation row never proves rollback.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.persistence.codec import FORMAT_VERSION, InvalidSnapshot, Snapshot, decode, encode
from app.persistence.config import DatabaseConfig
from app.persistence.schema import SCHEMA_REVISION, events, rooms, sessions, snapshots

KINDS = frozenset({
    "room:create", "room:join", "room:quit", "room:expire", "room:recover",
    "session:attach", "session:detach", "player:remove", "presenter:transfer",
    "player:rename", "player:set_avatar", "theme:add", "theme:remove", "theme:select",
    "game:start", "game:reset", "game:end_early", "choice:reveal", "timer:start",
    "answer:good", "answer:bad", "answer:pass", "answer:continue", "answer:vault",
})


class PersistenceUnavailable(Exception):
    code = "persistence_unavailable"
    message = "Room persistence unavailable."

    def __init__(self):
        super().__init__(self.message)


class RevisionConflict(PersistenceUnavailable):
    pass


class CommitUnknown(PersistenceUnavailable):
    pass


@dataclass(frozen=True)
class Event:
    kind: str
    occurred_at: datetime
    actor_id: UUID | None = None
    target_id: UUID | None = None

    def __post_init__(self):
        if (self.kind not in KINDS or not isinstance(self.occurred_at, datetime)
                or self.occurred_at.utcoffset() != timezone.utc.utcoffset(None)
                or any(v is not None and type(v) is not UUID for v in (self.actor_id, self.target_id))):
            raise ValueError("Invalid persistence event.")


class PostgresStore:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        url = make_url(config.url).set(drivername="postgresql+asyncpg")
        self._engine = create_async_engine(
            url, pool_size=config.pool_size, max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout, pool_pre_ping=True,
            hide_parameters=True, echo=False,
            connect_args=config.connect_args(),
        )

    async def _cleanup(self, connection, proxy, transaction=None, *, discard=False):
        """One extra budget, even under repeated caller cancellation; never retry SQL."""
        terminated = False

        def terminate():
            nonlocal terminated
            if terminated:
                return
            terminated = True
            # Detach returns the pool slot without doing network IO. asyncpg's
            # terminate is synchronous: no graceful close/rollback can outlive us.
            try:
                driver = proxy.driver_connection
                try:
                    proxy.detach()
                finally:
                    driver.terminate()
            except Exception:
                pass

        async def release():
            if discard:
                terminate()
            elif transaction is not None:
                await transaction.rollback()
            await connection.close()

        task = asyncio.create_task(release())
        deadline = asyncio.get_running_loop().time() + self.config.cleanup_timeout
        cancelled = False
        try:
            while not task.done():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait({task}, timeout=remaining)
                except asyncio.CancelledError:
                    cancelled = True
            if not task.done():
                terminate()
                task.cancel()
                # Do not wait for a cancellation-resistant driver finalizer.
                task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
                raise PersistenceUnavailable()
            try:
                task.result()
            except BaseException:
                terminate()
                raise PersistenceUnavailable() from None
        finally:
            if cancelled:
                raise asyncio.CancelledError()

    @asynccontextmanager
    async def connection(self, timeout=None):
        """Bound reads/migrations plus the same independent release budget."""
        connection = self._engine.connect()
        proxy = None
        try:
            async with asyncio.timeout(timeout or self.config.transaction_timeout):
                await connection.__aenter__()
                proxy = connection.sync_connection.connection
                yield connection
        finally:
            if proxy is not None:
                pending = sys.exception()
                try:
                    await self._cleanup(connection, proxy)
                except PersistenceUnavailable:
                    if pending is None:
                        raise

    async def close(self) -> None:
        async with asyncio.timeout(self.config.transaction_timeout):
            await self._engine.dispose()

    async def check(self) -> None:
        try:
            async with self.connection() as connection:
                heads = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalars().all()
                if heads != [SCHEMA_REVISION]:
                    raise PersistenceUnavailable()
        except Exception:
            raise PersistenceUnavailable() from None

    async def _read(self, connection, row) -> Snapshot:
        saved = (await connection.execute(sa.select(snapshots).where(
            snapshots.c.room_id == row["room_id"], snapshots.c.revision == row["revision"],
        ))).mappings().one()
        candidate = decode(json.dumps(saved["payload"]))
        if (saved["format_version"] != FORMAT_VERSION or saved["game_id"] != candidate.game_id
                or saved["write_id"] != candidate.write_id):
            raise InvalidSnapshot()
        for key in ("room_id", "code", "status", "game_id", "revision", "write_id",
                    "created_at", "closed_at", "idle_deadline_utc", "last_liveness_at"):
            if row[key] != getattr(candidate, key):
                raise InvalidSnapshot()
        records = (await connection.execute(sa.select(sessions).where(
            sessions.c.room_id == candidate.room_id, sessions.c.revision == candidate.revision,
        ))).mappings().all()
        actual = {r["participant_id"]: (r["proof_digest"], r["role"], r["status"], r["created_at"], r["revoked_at"])
                  for r in records}
        expected = {s.participant_id: (bytes.fromhex(s.proof_digest), s.role, s.status, s.created_at, s.revoked_at)
                    for s in candidate.sessions}
        if actual != expected:
            raise InvalidSnapshot()
        return candidate

    async def load_live(self) -> tuple[Snapshot, ...]:
        """Reject the entire restore on corruption; never skip malformed rooms."""
        try:
            async with self.connection() as connection:
                await connection.begin()
                await connection.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                rows = (await connection.execute(sa.select(rooms).where(rooms.c.status == "live"))).mappings().all()
                return tuple([await self._read(connection, row) for row in rows])
        except Exception:
            raise PersistenceUnavailable() from None

    async def write(self, candidate: Snapshot, expected_revision: int, event: Event | None) -> None:
        payload = json.loads(encode(candidate))
        if (type(expected_revision) is not int or expected_revision < 0
                or candidate.revision != expected_revision + 1
                or (event is not None and type(event) is not Event)):
            raise ValueError("Invalid candidate revision/event.")
        if expected_revision == 0 and (event is None or event.kind != "room:create" or candidate.status != "live"):
            raise ValueError("Creation requires a live room and event.")
        if event is not None and any(pid is not None and pid not in {s.participant_id for s in candidate.sessions}
                                     for pid in (event.actor_id, event.target_id)):
            raise ValueError("Invalid event participant.")
        submitted = False
        committed = False
        connection = None
        proxy = None
        transaction = None
        try:
            try:
                async with asyncio.timeout(self.config.transaction_timeout):
                    connection = self._engine.connect()
                    await connection.__aenter__()
                    proxy = connection.sync_connection.connection
                    transaction = await connection.begin()
                    values = {key: getattr(candidate, key) for key in (
                        "room_id", "code", "status", "game_id", "revision", "write_id", "created_at",
                        "closed_at", "idle_deadline_utc", "last_liveness_at")}
                    if expected_revision == 0:
                        await connection.execute(sa.insert(rooms).values(**values))
                    else:
                        previous_row = (await connection.execute(sa.select(rooms).where(
                            rooms.c.room_id == candidate.room_id,
                        ).with_for_update(nowait=True))).mappings().one_or_none()
                        if previous_row is None or previous_row["revision"] != expected_revision:
                            raise RevisionConflict()
                        previous = await self._read(connection, previous_row)
                        self._validate_transition(previous, candidate, event)
                        result = await connection.execute(sa.update(rooms).where(
                            rooms.c.room_id == candidate.room_id, rooms.c.revision == expected_revision,
                        ).values(**values))
                        if result.rowcount != 1:
                            raise RevisionConflict()
                    await connection.execute(sa.insert(snapshots).values(
                        room_id=candidate.room_id, revision=candidate.revision, game_id=candidate.game_id,
                        write_id=candidate.write_id, format_version=FORMAT_VERSION, payload=payload,
                    ))
                    if candidate.sessions:
                        await connection.execute(sa.insert(sessions), [{
                            "room_id": candidate.room_id, "revision": candidate.revision,
                            "participant_id": s.participant_id, "proof_digest": bytes.fromhex(s.proof_digest),
                            "role": s.role, "status": s.status, "created_at": s.created_at, "revoked_at": s.revoked_at,
                        } for s in candidate.sessions])
                    if event is not None:
                        await connection.execute(sa.insert(events).values(
                            event_id=candidate.write_id, room_id=candidate.room_id,
                            revision=candidate.revision, game_id=candidate.game_id,
                            occurred_at=event.occurred_at, kind=event.kind,
                            actor_id=event.actor_id, target_id=event.target_id,
                        ))
                    submitted = True
                    await transaction.commit()
                    committed = True
            finally:
                if connection is not None and proxy is not None:
                    pending = sys.exception()
                    try:
                        await self._cleanup(connection, proxy,
                                            transaction if not submitted else None,
                                            discard=submitted and not committed)
                    except PersistenceUnavailable:
                        if pending is None:
                            raise
        except RevisionConflict:
            raise
        except BaseException as exc:
            if submitted:
                raise CommitUnknown() from None
            if isinstance(exc, asyncio.CancelledError):
                raise
            if not isinstance(exc, Exception):
                raise
            raise PersistenceUnavailable() from None

    @staticmethod
    def _validate_transition(previous: Snapshot, candidate: Snapshot, event: Event | None) -> None:
        if (previous.status != "live" or previous.code != candidate.code
                or previous.created_at != candidate.created_at or previous.write_id == candidate.write_id
                or ((previous.game_id != candidate.game_id) != (event is not None and event.kind == "game:reset"))
                or (event is not None and event.kind == "room:create")
                or candidate.last_liveness_at < previous.last_liveness_at):
            raise InvalidSnapshot()
        current = {s.participant_id: s for s in candidate.sessions}
        for old in previous.sessions:
            new = current.get(old.participant_id)
            if (new is None or new.proof_digest != old.proof_digest or new.created_at != old.created_at
                    or (old.status == "revoked" and new != old)):
                raise InvalidSnapshot()
        if event is None:
            # A heartbeat may renew only durable liveness, not gameplay/session state.
            if (previous.state != candidate.state or previous.sessions != candidate.sessions
                    or previous.presenter_id != candidate.presenter_id or previous.status != candidate.status
                    or previous.game_id != candidate.game_id):
                raise InvalidSnapshot()

    async def reconcile(self, candidate: Snapshot, expected_revision: int) -> Literal["committed", "not_committed", "blocked"]:
        """One bounded authoritative readback; no retry, replay or assumed rollback."""
        encode(candidate)
        try:
            async with self.connection(self.config.reconcile_timeout) as connection:
                await connection.begin()
                row = (await connection.execute(sa.select(rooms).where(
                    rooms.c.room_id == candidate.room_id,
                ).with_for_update(nowait=True))).mappings().one_or_none()
                if row is None:
                    return "blocked"
                saved = await self._read(connection, row)
                if saved == candidate:
                    return "committed"
                # Acquiring the row lock proves the preceding writer has resolved.
                if saved.revision == expected_revision and expected_revision > 0:
                    return "not_committed"
                return "blocked"
        except Exception:
            return "blocked"
