"""Unit tests for the shared transient-retry helper.

The retry policy is exercised in two places (alembic env.py and
admin.push_tle_feed); both rely on the same `run_with_db_retry`. The
behaviour we care about is narrow:

- Transient `asyncpg.ConnectionDoesNotExistError` (wrapped in SQLAlchemy
  or surfaced raw) triggers a retry.
- Non-transient exceptions propagate immediately.
- The factory is called fresh each attempt so the caller can supply a
  new session per try.
"""

import asyncpg.exceptions
import pytest

from app.services.db_retry import is_transient_db_error, run_with_db_retry


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip the real backoff so retry tests stay sub-millisecond. Patch
    on the retry module's namespace, not asyncio itself, to avoid
    recursive sleep-calling-sleep loops."""

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr("app.services.db_retry.asyncio.sleep", _noop)


def test_is_transient_unwraps_cause_chain():
    inner = asyncpg.exceptions.ConnectionDoesNotExistError(
        "connection was closed in the middle of operation"
    )
    outer = RuntimeError("wrapped by SQLAlchemy")
    outer.__cause__ = inner
    assert is_transient_db_error(outer)


def test_is_transient_rejects_unrelated_error():
    assert not is_transient_db_error(ValueError("not a connection error"))


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = []

    async def factory():
        calls.append(1)
        if len(calls) < 3:
            raise asyncpg.exceptions.ConnectionDoesNotExistError("transient")
        return "ok"

    result = await run_with_db_retry(factory, label="test", attempts=4)
    assert result == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_propagates_non_transient_immediately():
    calls = []

    async def factory():
        calls.append(1)
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        await run_with_db_retry(factory, label="test", attempts=4)
    # No retry — fail on the first attempt.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_gives_up_after_exhausting_attempts():
    calls = []

    async def factory():
        calls.append(1)
        raise asyncpg.exceptions.ConnectionDoesNotExistError("persistent")

    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await run_with_db_retry(factory, label="test", attempts=3)
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_factory_called_freshly_each_attempt():
    """Same-session retry is doomed — callers rely on the factory being
    invoked anew each attempt so they can build a fresh DB session."""
    factory_invocations: list[object] = []

    async def factory():
        token = object()
        factory_invocations.append(token)
        if len(factory_invocations) < 2:
            raise asyncpg.exceptions.ConnectionDoesNotExistError("once")
        return token

    result = await run_with_db_retry(factory, label="test", attempts=3)
    # Same token returned only on the final attempt; the earlier call
    # produced a distinct object that never returned.
    assert result is factory_invocations[-1]
    assert factory_invocations[0] is not factory_invocations[-1]
