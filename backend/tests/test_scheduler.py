from unittest.mock import AsyncMock, patch

import pytest

from app.services.scheduler import refresh_tle_job


@pytest.mark.asyncio
async def test_refresh_clears_cache_when_snapshots_stored():
    with (
        patch(
            "app.services.scheduler.refresh_tle",
            new_callable=AsyncMock,
            return_value=150,
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch(
            "app.services.scheduler.warm_positions_cache",
            new_callable=AsyncMock,
        ),
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle_job()

    assert mock_clear.call_count == 2
    mock_clear.assert_any_call("satlas:overhead:*")
    mock_clear.assert_any_call("satlas:positions*")


@pytest.mark.asyncio
async def test_refresh_skips_cache_clear_when_no_new_data():
    with (
        patch(
            "app.services.scheduler.refresh_tle",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle_job()

    mock_clear.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_handles_exception_gracefully():
    """Any exception from refresh_tle must not propagate — job must not crash."""
    with (
        patch(
            "app.services.scheduler.refresh_tle",
            new_callable=AsyncMock,
            side_effect=Exception("network failure"),
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle_job()  # must not raise

    mock_clear.assert_not_called()
