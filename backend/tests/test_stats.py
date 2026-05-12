"""Integration tests for /stats/dashboard.

Cache layer + the top-countries Redis pipeline are mocked; the SQL aggregations
hit a fresh `_satellite_totals` / `_recent_launches` query against an in-memory
async surface (db.execute returns canned rows). DB-side correctness belongs in
a real-PG integration test (Issue #11) — these tests cover the wiring and the
cache-hit shortcut.
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.boundaries import load_country_polygons


@pytest.fixture(autouse=True, scope="session")
def _polygons():
    load_country_polygons()


@pytest.fixture
def client():
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


def test_returns_cached_payload_verbatim(client):
    cached = json.dumps(
        {
            "satellites": {"total": 5234, "by_category": {"STATION": 3}},
            "top_countries": [{"cc": "RU", "passes_24h": 1234}],
            "recent_launches": [],
        }
    )
    with patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget:
        mget.return_value = cached
        resp = client.get("/stats/dashboard")

    assert resp.status_code == 200
    body = resp.json()
    assert body["satellites"]["total"] == 5234
    assert body["top_countries"][0]["cc"] == "RU"


def test_computes_and_caches_when_miss(client):
    """On cache miss, runs the three sub-computations and writes the cache."""
    # Cache miss
    with (
        patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget,
        patch("app.services.cache.cache_set", new_callable=AsyncMock) as mset,
        patch("app.routers.stats._satellite_totals", new_callable=AsyncMock) as msat,
        patch("app.routers.stats._top_countries", new_callable=AsyncMock) as mtop,
        patch("app.routers.stats._recent_launches", new_callable=AsyncMock) as mrec,
    ):
        mget.return_value = None
        msat.return_value = {"total": 100, "by_category": {"STATION": 3}}
        mtop.return_value = [{"cc": "US", "passes_24h": 42}]
        mrec.return_value = [
            {
                "norad_id": 1,
                "name": "SAT-1",
                "launch_date": "2026-05-01",
                "operator": "US",
                "category": "COMMERCIAL",
            }
        ]

        resp = client.get("/stats/dashboard")

    assert resp.status_code == 200
    body = resp.json()
    assert body["satellites"]["total"] == 100
    assert body["top_countries"][0]["cc"] == "US"
    assert body["recent_launches"][0]["norad_id"] == 1

    # Cache was written (single call after compute)
    assert mset.await_count == 1
    args, kwargs = mset.call_args
    assert args[0] == "satlas:stats:dashboard"
    assert "satellites" in args[1]  # serialized JSON contains the payload
    assert kwargs.get("ttl") == 300


def test_top_countries_aggregates_pipeline_results():
    """Aggregation: hash values are summed, zero-totals are dropped, sorted desc."""
    from app.routers.stats import _top_countries

    # Inject 4 fake countries via boundaries module's polygon dict.
    fake_polys = {"AA": object(), "BB": object(), "CC": object(), "DD": object()}
    pipeline_result = [
        {"25544": "10", "100": "5"},  # AA: 15
        {"25544": "100", "200": "50"},  # BB: 150
        {},  # CC: missing (skipped)
        {"100": "0"},  # DD: 0 (skipped — only positive totals)
    ]

    with (
        patch.dict("app.services.boundaries._country_polygons", fake_polys, clear=True),
        patch(
            "app.services.cache.cache_pipeline_hgetall",
            new_callable=AsyncMock,
            return_value=pipeline_result,
        ),
    ):
        import asyncio

        out = asyncio.get_event_loop().run_until_complete(_top_countries())

    # Sorted descending, zero/missing rows dropped.
    assert out == [
        {"cc": "BB", "passes_24h": 150},
        {"cc": "AA", "passes_24h": 15},
    ]


def test_top_countries_tolerates_non_numeric_hash_values():
    """Garbage values in a visit hash don't crash the aggregator."""
    from app.routers.stats import _top_countries

    fake_polys = {"AA": object()}
    pipeline_result = [{"25544": "not-a-number", "100": "5"}]

    with (
        patch.dict("app.services.boundaries._country_polygons", fake_polys, clear=True),
        patch(
            "app.services.cache.cache_pipeline_hgetall",
            new_callable=AsyncMock,
            return_value=pipeline_result,
        ),
    ):
        import asyncio

        out = asyncio.get_event_loop().run_until_complete(_top_countries())

    assert out == [{"cc": "AA", "passes_24h": 5}]


def test_top_countries_empty_when_no_polygons_loaded():
    from app.routers.stats import _top_countries

    with patch.dict("app.services.boundaries._country_polygons", {}, clear=True):
        import asyncio

        out = asyncio.get_event_loop().run_until_complete(_top_countries())

    assert out == []
