import asyncio
import logging
from logging.config import fileConfig

import asyncpg.exceptions
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.satellite  # noqa: F401
import app.models.user  # noqa: F401
from alembic import context
from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

logger = logging.getLogger("alembic.runtime.migration")

# release_command machines on Fly are short-lived and have hit transient
# `ConnectionDoesNotExistError: connection was closed in the middle of
# operation` on the very first Postgres call multiple times. The DB itself
# is fine on retry — wrap the migration entrypoint in bounded retries.
_RETRY_LIMIT = 4
_RETRY_BACKOFF_SECONDS = 2

_TRANSIENT = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.CannotConnectNowError,
    ConnectionResetError,
    ConnectionRefusedError,
    OSError,
)


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _attempt_migrations():
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


def _is_transient(exc: BaseException) -> bool:
    cause = exc
    while cause is not None:
        if isinstance(cause, _TRANSIENT):
            return True
        cause = cause.__cause__
    return False


async def run_async_migrations():
    for attempt in range(1, _RETRY_LIMIT + 1):
        try:
            await _attempt_migrations()
            return
        except (DBAPIError, OSError) as exc:
            if not _is_transient(exc) or attempt == _RETRY_LIMIT:
                raise
            wait = _RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "Transient DB error on migration attempt %d/%d (%s). Retrying in %ds.",
                attempt,
                _RETRY_LIMIT,
                exc.__class__.__name__,
                wait,
            )
            await asyncio.sleep(wait)


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    raise NotImplementedError("Offline migrations are not supported.")
else:
    run_migrations_online()
