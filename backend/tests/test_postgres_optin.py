"""Future dedicated Postgres only. Creates retained archives, never drops data."""

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from app.persistence.config import DatabaseConfig
from app.persistence.schema import events, sessions, snapshots
from app.persistence.store import Event, PostgresStore, RevisionConflict
from tests.test_persistence import candidate  # explicit test-only snapshot fixture


@pytest.fixture
def dedicated_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL absent: real Postgres validation deferred; no substitute database.")
    try:
        parsed = make_url(url)
        same_database = False
        for production in (os.environ.get("DATABASE_PRIVATE_URL"), os.environ.get("DATABASE_URL")):
            if not production:
                continue
            deployed = make_url(production)
            same_database |= (parsed.host, parsed.port or 5432, parsed.database) == (
                deployed.host, deployed.port or 5432, deployed.database)
        safe = (parsed.database.endswith("_test") and not same_database
                and os.environ.get("TEST_DATABASE_ACK") == "dedicated-disposable-database")
    except Exception:
        safe = False
    if not safe:
        pytest.fail("Refusing database tests: require distinct dedicated *_test database and TEST_DATABASE_ACK.")
    return DatabaseConfig(url, tls_mode=os.environ.get("DB_TLS_MODE", "verify-full"))


@pytest.mark.asyncio
async def test_postgres_atomic_archive_occ_and_restore(dedicated_database, candidate):
    store = PostgresStore(dedicated_database)
    try:
        # An operator must explicitly migrate the future dedicated database first.
        await store.check()
        await store.write(candidate, 0, Event("room:create", candidate.created_at))
        assert candidate in await store.load_live()
        assert await store.reconcile(candidate, 0) == "committed"
        closed = candidate.model_copy(update={
            "revision": 2, "write_id": uuid4(), "status": "closed", "closed_at": candidate.created_at,
            "sessions": tuple(s.model_copy(update={"status": "revoked", "revoked_at": candidate.created_at})
                              for s in candidate.sessions),
        })
        await store.write(closed, 1, Event("room:quit", candidate.created_at))
        with pytest.raises(RevisionConflict):
            await store.write(closed.model_copy(update={"write_id": uuid4()}), 1,
                              Event("room:quit", candidate.created_at))
        assert all(s.room_id != candidate.room_id for s in await store.load_live())
        async with store._engine.connect() as connection:
            for table, count in ((snapshots, 2), (sessions, 2), (events, 2)):
                actual = await connection.scalar(sa.select(sa.func.count()).select_from(table).where(
                    table.c.room_id == candidate.room_id))
                assert actual == count
    finally:
        await store.close()
