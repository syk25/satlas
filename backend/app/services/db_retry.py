"""Bounded retry for transient asyncpg connection drops.

The Fly-hosted Postgres cluster (satlas-db-sjc) occasionally drops the
client connection mid-statement — at most once a day or two, brief enough
that the next attempt against a fresh connection succeeds. The alembic
release_command saw this regularly enough to warrant a retry wrapper
(ADR-019); the same shape also surfaces during the GHA TLE-refresh cron
when `ingest_feed` upserts a 16k-satellite batch. Sharing the helper
keeps the retry policy in one place.

The factory pattern is load-bearing: same-session retry after a broken
connection is doomed, so the caller must hand us a coroutine factory that
constructs a fresh DB session each attempt.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import asyncpg.exceptions

logger = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 2

_TRANSIENT_TYPES: tuple[type[BaseException], ...] = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.CannotConnectNowError,
    ConnectionResetError,
    ConnectionRefusedError,
    OSError,
)


def is_transient_db_error(exc: BaseException) -> bool:
    """Walk the `__cause__` chain looking for any transient connection drop.
    SQLAlchemy wraps the underlying asyncpg exception, so checking the
    outer type alone misses the case we care about."""
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, _TRANSIENT_TYPES):
            return True
        cause = cause.__cause__
    return False


T = TypeVar("T")


async def run_with_db_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
    label: str = "db op",
) -> T:
    """Call `coro_factory()` up to `attempts` times, retrying only on
    transient asyncpg connection drops. Backoff scales linearly with the
    attempt number (2s, 4s, 6s, 8s by default). Non-transient errors
    propagate immediately; the final attempt's exception propagates if
    all retries are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not is_transient_db_error(exc) or attempt == attempts:
                raise
            wait = backoff_seconds * attempt
            logger.warning(
                "Transient DB error on %s attempt %d/%d (%s). Retrying in %ds.",
                label,
                attempt,
                attempts,
                exc.__class__.__name__,
                wait,
            )
            await asyncio.sleep(wait)
    # Unreachable in practice — the final attempt either returns or
    # re-raises above. The line exists so type checkers see a clear
    # post-condition rather than implicit None return.
    raise RuntimeError(f"run_with_db_retry exhausted without raising: {last_exc!r}")
