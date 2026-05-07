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
async def test_refresh_tle_skips_cache_clear_when_no_new_data():
    with (
        patch(
            "app.services.scheduler.fetch_and_store_tle",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "app.services.scheduler.cache_clear_pattern",
            new_callable=AsyncMock,
        ) as mock_clear,
        patch("app.services.scheduler.AsyncSessionLocal"),
    ):
        await refresh_tle()

    mock_clear.assert_not_called()


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
