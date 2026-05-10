"""Unit tests for the Celery prewarm tasks (ADR-021).

The fan-out task is sync; the per-country worker body is async (run via
asyncio.run by Celery), so it's tested directly as a coroutine.
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
    """Patch the Redis-touching helpers used by _run_one."""
    with (
        patch("app.services.cache.init_redis", new_callable=AsyncMock),
        patch("app.services.cache.close_redis", new_callable=AsyncMock),
        patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget,
        patch("app.services.cache.cache_set", new_callable=AsyncMock) as mset,
        patch("app.services.cache.cache_hash_mget", new_callable=AsyncMock) as mhmget,
    ):
        yield {"get": mget, "set": mset, "hmget": mhmget}


# ── per-country worker (_run_one) ──


@pytest.mark.asyncio
async def test_run_one_skips_when_positions_cache_empty(cache_module):
    cache_module["get"].return_value = None
    from app.tasks import _run_one

    result = await _run_one("KR")

    assert result["skipped"] is True
    assert result["cc"] == "KR"
    cache_module["set"].assert_not_called()


@pytest.mark.asyncio
async def test_run_one_writes_cache_when_country_has_rows(cache_module):
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

    def fake_simulate(cc, candidates, now):
        from datetime import timedelta

        return [
            {
                **sample_position,
                "entry_time": now,
                "exit_time": now + timedelta(minutes=5),
            }
        ]

    with patch(
        "app.services.overhead_simulation.simulate_overhead_window",
        side_effect=fake_simulate,
    ):
        from app.tasks import _run_one

        result = await _run_one("KR")

    assert result["cc"] == "KR"
    assert result["rows"] == 1
    set_keys = [call.args[0] for call in cache_module["set"].call_args_list]
    assert set_keys == ["satlas:overhead:KR"]


@pytest.mark.asyncio
async def test_run_one_writes_empty_payload_when_no_rows(cache_module):
    cache_module["get"].return_value = json.dumps([])

    async def fake_hmget(_key, fields):
        return [None] * len(fields)

    cache_module["hmget"].side_effect = fake_hmget

    with patch(
        "app.services.overhead_simulation.simulate_overhead_window",
        return_value=[],
    ):
        from app.tasks import _run_one

        result = await _run_one("KR")

    assert result["rows"] == 0
    # Empty result still gets cached so users see "no satellites" instantly
    # instead of falling through to a 5-second lazy path.
    set_keys = [call.args[0] for call in cache_module["set"].call_args_list]
    assert set_keys == ["satlas:overhead:KR"]


# ── fan-out dispatcher ──


def test_fanout_dispatches_one_task_per_country():
    """The beat-fired task should call .delay() once per loaded country and
    return the dispatched count."""
    from app.tasks import (
        prewarm_overhead_all_countries,
        prewarm_overhead_one_country,
    )

    with patch.object(prewarm_overhead_one_country, "delay") as mock_delay:
        result = prewarm_overhead_all_countries()

    assert result["countries_dispatched"] > 100  # 200+ countries loaded
    assert mock_delay.call_count == result["countries_dispatched"]
    # Every dispatched call carries a country code string (ISO-A2 plus the
    # disputed-territory codes from ADR-003, e.g. "CN-TW").
    for call in mock_delay.call_args_list:
        cc = call.args[0]
        assert isinstance(cc, str) and 2 <= len(cc) <= 8
