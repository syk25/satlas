"""Unit tests for the Celery prewarm task body (ADR-021).

Tests target the async coroutine `_run_prewarm` directly — Celery's sync
wrapper just calls `asyncio.run`, which we don't need to validate.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.boundaries import load_country_polygons

ISS_LINE1 = "1 25544U 98067A   26129.50000000  .00000000  00000-0  00000-0 0  9999"
ISS_LINE2 = "2 25544  51.6406  21.3520 0006703  61.6303  21.5517 15.49327394434245"


@pytest.fixture(autouse=True, scope="session")
def _polygons():
    load_country_polygons()


@pytest.fixture
def cache_module():
    """Patch out the Redis-touching helpers used by _run_prewarm."""
    with (
        patch("app.services.cache.init_redis", new_callable=AsyncMock),
        patch("app.services.cache.close_redis", new_callable=AsyncMock),
        patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget,
        patch("app.services.cache.cache_set", new_callable=AsyncMock) as mset,
        patch("app.services.cache.cache_hash_mget", new_callable=AsyncMock) as mhmget,
    ):
        yield {"get": mget, "set": mset, "hmget": mhmget}


@pytest.mark.asyncio
async def test_prewarm_skips_when_positions_cache_empty(cache_module):
    cache_module["get"].return_value = None
    from app.tasks import _run_prewarm

    result = await _run_prewarm()
    assert result == {"skipped": True}
    cache_module["set"].assert_not_called()


@pytest.mark.asyncio
async def test_prewarm_writes_one_cache_entry_per_country(cache_module):
    sample_position = {
        "norad_id": 25544,
        "name": "ISS",
        "lat": 37.5,
        "lon": 127.0,
        "category": "STATION",
        "orbit_class": "LEO",
        "operator": "US",
        "launch_date": None,
        "decay_date": None,
        "international_designator": "1998-067A",
        "object_type": "PAYLOAD",
        "rcs_size": "LARGE",
        "line1": ISS_LINE1,
        "line2": ISS_LINE2,
    }
    cache_module["get"].return_value = json.dumps([sample_position])

    async def fake_hmget(_key, fields):
        return [None] * len(fields)

    cache_module["hmget"].side_effect = fake_hmget

    # Stub simulate_overhead_window to return one row for KR, empty elsewhere.
    def fake_simulate(cc, candidates, now):
        if cc == "KR":
            from datetime import timedelta

            return [
                {
                    **sample_position,
                    "entry_time": now,
                    "exit_time": now + timedelta(minutes=5),
                }
            ]
        return []

    with patch(
        "app.services.overhead_simulation.simulate_overhead_window",
        side_effect=fake_simulate,
    ):
        from app.tasks import _run_prewarm

        result = await _run_prewarm()

    assert result["countries_total"] > 100  # all loaded countries
    assert result["countries_ok"] == result["countries_total"]
    assert result["rows"] == 1  # only KR yielded a row
    assert result["failed"] == []
    # cache_set was called once per country with windowed rows.
    # Empty-result countries are skipped — only KR triggers a write.
    set_keys = [call.args[0] for call in cache_module["set"].call_args_list]
    assert "satlas:overhead:KR" in set_keys


@pytest.mark.asyncio
async def test_prewarm_records_failures_per_country(cache_module):
    cache_module["get"].return_value = json.dumps([])

    def fake_simulate(cc, candidates, now):
        if cc == "RU":
            raise RuntimeError("synthetic boom")
        return []

    with patch(
        "app.services.overhead_simulation.simulate_overhead_window",
        side_effect=fake_simulate,
    ):
        from app.tasks import _run_prewarm

        result = await _run_prewarm()

    assert "RU" in result["failed"]
    assert result["countries_ok"] == result["countries_total"] - 1
