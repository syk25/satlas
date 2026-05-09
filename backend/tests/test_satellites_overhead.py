"""Integration tests for /satellites/overhead — covers routing, caching, and
the passes_24h enrichment introduced by ADR-019.

The router itself does not touch the DB — it reads precomputed positions from
Redis and delegates simulation to overhead_simulation. Tests therefore mock
only the cache layer and the simulation function; ADR-010's "no DB mocks"
rule is respected because no DB calls happen on this path.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.boundaries import load_country_polygons
from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY


@pytest.fixture(autouse=True, scope="session")
def _polygons():
    load_country_polygons()


@pytest.fixture
def client():
    """TestClient with the production lifespan replaced by a minimal one
    that only loads boundaries — no DB, Redis, or scheduler startup."""

    @asynccontextmanager
    async def test_lifespan(_app):
        load_country_polygons()
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = test_lifespan
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.router.lifespan_context = original


# ── Sample data shaped like what warm_positions_cache produces ──

ISS_LINE1 = "1 25544U 98067A   26129.50000000  .00000000  00000-0  00000-0 0  9999"
ISS_LINE2 = "2 25544  51.6406  21.3520 0006703  61.6303  21.5517 15.49327394434245"


def _sample_position() -> dict:
    return {
        "norad_id": 25544,
        "name": "ISS (ZARYA)",
        "lat": 37.5,
        "lon": 127.0,
        "category": "STATION",
        "orbit_class": "LEO",
        "operator": "US",
        "launch_date": "1998-11-20",
        "decay_date": None,
        "international_designator": "1998-067A",
        "object_type": "PAYLOAD",
        "rcs_size": "LARGE",
        "line1": ISS_LINE1,
        "line2": ISS_LINE2,
    }


def _windowed_row(now: datetime) -> dict:
    """One row in the shape simulate_overhead_window returns."""
    return {
        **_sample_position(),
        "entry_time": now,
        "exit_time": now + timedelta(minutes=5),
    }


# ── Tests ──


def test_overhead_invalid_country(client):
    response = client.get("/satellites/overhead/XX")
    assert response.status_code == 404


def test_overhead_unknown_category_400(client):
    response = client.get("/satellites/overhead/KR?category=NOT_A_THING")
    assert response.status_code == 400


def test_overhead_no_position_cache_returns_503(client):
    """When the positions pre-cache (ADR-016) hasn't warmed yet, /overhead
    should return 503 rather than serve stale or empty data silently."""
    with patch(
        "app.routers.satellites.cache.cache_get",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 503
    assert "not yet available" in response.json()["detail"].lower()


def test_overhead_cache_hit_skips_simulation(client):
    """Pre-warmed overhead cache should be returned verbatim without invoking
    the simulation. The cached payload must include the passes_24h field
    introduced by ADR-019."""
    now = datetime.now(timezone.utc)
    cached = [
        {
            "norad_id": 25544,
            "name": "ISS (ZARYA)",
            "category": "STATION",
            "operator": "US",
            "operator_name": None,
            "operator_type": None,
            "orbit_class": "LEO",
            "launch_date": "1998-11-20",
            "decay_date": None,
            "international_designator": "1998-067A",
            "object_type": "PAYLOAD",
            "rcs_size": "LARGE",
            "line1": ISS_LINE1,
            "line2": ISS_LINE2,
            "entry_time": now.isoformat(),
            "exit_time": (now + timedelta(minutes=5)).isoformat(),
            "passes_24h": 7,
        }
    ]

    async def fake_cache_get(key: str):
        if key.startswith("satlas:overhead:KR"):
            return json.dumps(cached)
        return None

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            side_effect=fake_cache_get,
        ),
        patch("app.routers.satellites.simulate_overhead_window") as mock_sim,
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["norad_id"] == 25544
    assert body[0]["passes_24h"] == 7
    mock_sim.assert_not_called()


def test_overhead_warm_path_includes_passes_24h(client):
    """Simulation cache miss + visit hash present → response carries the
    pass count looked up via HMGET (ADR-019 enrichment)."""
    now = datetime.now(timezone.utc)

    async def fake_cache_get(key: str):
        if key == POSITIONS_ALL_CACHE_KEY:
            return json.dumps([_sample_position()])
        return None  # overhead cache miss

    async def fake_hash_mget(_key: str, fields: list[str]):
        # Pretend the precompute saw the ISS pass over Korea 7 times.
        return ["7" if f == "25544" else None for f in fields]

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            side_effect=fake_cache_get,
        ),
        patch(
            "app.routers.satellites.cache.cache_hash_mget",
            side_effect=fake_hash_mget,
        ),
        patch(
            "app.routers.satellites.cache.cache_set",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.satellites.simulate_overhead_window",
            return_value=[_windowed_row(now)],
        ),
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["norad_id"] == 25544
    assert body[0]["passes_24h"] == 7
    assert body[0]["entry_time"]
    assert body[0]["exit_time"]


def test_overhead_warm_path_passes_24h_null_when_precompute_pending(client):
    """Visit precompute hasn't run yet → passes_24h gracefully degrades to
    null instead of erroring or hiding the satellite."""
    now = datetime.now(timezone.utc)

    async def fake_cache_get(key: str):
        if key == POSITIONS_ALL_CACHE_KEY:
            return json.dumps([_sample_position()])
        return None

    async def fake_hash_mget(_key: str, fields: list[str]):
        return [None for _ in fields]

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            side_effect=fake_cache_get,
        ),
        patch(
            "app.routers.satellites.cache.cache_hash_mget",
            side_effect=fake_hash_mget,
        ),
        patch(
            "app.routers.satellites.cache.cache_set",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.satellites.simulate_overhead_window",
            return_value=[_windowed_row(now)],
        ),
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["passes_24h"] is None
