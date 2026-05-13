import asyncio
import logging
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

import app.models.satellite  # noqa: F401
import app.models.user  # noqa: F401
from alembic import context
from app.config import settings
from app.models import Base
from app.services.db_retry import run_with_db_retry

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

logger = logging.getLogger("alembic.runtime.migration")


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _attempt_migrations():
    # Fresh engine per attempt — the retry helper depends on this so a
    # broken connection from a prior attempt doesn't leak into the next one.
    url = settings.async_database_url
    connect_args = (
        {"ssl": False} if any(h in url for h in ("flycast", ".internal")) else {}
    )
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


async def run_async_migrations():
    # ADR-019 retry pattern — release_command machines occasionally hit
    # `ConnectionDoesNotExistError` on their first Postgres call. The
    # helper is shared with admin.push_tle_feed (same flake shape under
    # the GHA TLE-refresh cron).
    await run_with_db_retry(_attempt_migrations, label="alembic migration")


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    raise NotImplementedError("Offline migrations are not supported.")
else:
    run_migrations_online()
