"""Explicit migrations only. Offline SQL needs no URL and opens no connection."""

import asyncio

from alembic import context

from app.persistence.schema import metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    from app.persistence.config import DatabaseConfig
    from app.persistence.store import PostgresStore

    store = PostgresStore(DatabaseConfig.from_environment())
    try:
        async with store.connection() as connection:
            await connection.run_sync(migrate)
    except Exception:
        raise RuntimeError("Postgres migration failed.") from None
    finally:
        await store.close()


if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
