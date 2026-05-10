"""Unit tests for the Celery prewarm task (ADR-021 + 022).

The Celery task body is async (run via asyncio.run); these tests exercise
the coroutine directly. Redis-touching helpers and the propagation step are
patched so the test focuses on the task's control flow and contract:
which countries get cached, when the task short-circuits.
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
    """Patch the Redis-touching helpers used by _run_sweep."""
    with (
        patch("app.services.cache.init_redis", new_callable=AsyncMock),
        patch("app.services.cache.close_redis", new_callable=AsyncMock),
        patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget,
        patch("app.services.cache.cache_set", new_callable=AsyncMock) as mset,
        patch("app.services.cache.cache_hash_mget", new_callable=AsyncMock) as mhmget,
    ):
        yield {"get": mget, "set": mset, "hmget": mhmget}


@pytest.mark.asyncio
async def test_run_sweep_skips_when_positions_cache_empty(cache_module):
    cache_module["get"].return_value = None
    from app.tasks import _run_sweep

    result = await _run_sweep()

    assert result["skipped"] is True
    cache_module["set"].assert_not_called()


@pytest.mark.asyncio
async def test_run_sweep_writes_one_cache_entry_per_country(cache_module):
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

    # Skip the SGP4 work entirely; the test cares about loop structure, not
    # propagation correctness (covered separately in overhead_simulation tests).
    with (
        patch(
            "app.services.overhead_simulation.compute_window_positions",
            return_value=[],
        ),
        patch(
            "app.services.overhead_simulation.find_overhead_in_window",
            return_value=[],
        ),
    ):
        from app.services import boundaries
        from app.tasks import _run_sweep

        result = await _run_sweep()

    assert result["countries"] == len(boundaries._country_polygons)
    set_keys = [call.args[0] for call in cache_module["set"].call_args_list]
    # Every loaded country should get exactly one cache key written.
    assert len(set_keys) == len(boundaries._country_polygons)
    assert all(k.startswith("satlas:overhead:") for k in set_keys)
    # Every country code (ISO-A2 plus disputed-territory codes from ADR-003,
    # e.g. "CN-TW") shows up as a key suffix.
    cc_set = {k.removeprefix("satlas:overhead:") for k in set_keys}
    assert cc_set == {cc.upper() for cc in boundaries._country_polygons.keys()}
