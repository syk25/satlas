from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.scheduler import refresh_tle


@pytest.mark.asyncio
async def test_refresh_tle_clears_cache_on_new_data():
    with (
        patch(
            "app.services.scheduler.fetch_and_store_tle",
            new_callable=AsyncMock,
            return_value=100,
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle()

    mock_clear.assert_called_once_with("satlas:overhead:*")


@pytest.mark.asyncio
async def test_refresh_tle_falls_back_to_stations_only_when_db_empty():
    """Stations fallback runs only when DB is empty."""
    mock_fetch = AsyncMock(return_value=0)
    mock_snapshots = AsyncMock(return_value=[])

    with (
        patch("app.services.scheduler.fetch_and_store_tle", mock_fetch),
        patch("app.services.scheduler.get_latest_tle_snapshots", mock_snapshots),
        patch("app.services.scheduler.cache_clear_pattern", new_callable=AsyncMock),
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle()

    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_refresh_tle_skips_stations_fallback_when_db_has_data():
    """Skip stations fallback when DB already has satellite data."""
    mock_fetch = AsyncMock(return_value=0)
    mock_snapshots = AsyncMock(return_value=[object()])  # non-empty

    with (
        patch("app.services.scheduler.fetch_and_store_tle", mock_fetch),
        patch("app.services.scheduler.get_latest_tle_snapshots", mock_snapshots),
        patch("app.services.scheduler.cache_clear_pattern", new_callable=AsyncMock),
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle()

    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_refresh_tle_handles_celestrak_unavailable():
    with (
        patch(
            "app.services.scheduler.fetch_and_store_tle",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("connection failed"),
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle()

    mock_clear.assert_not_called()
