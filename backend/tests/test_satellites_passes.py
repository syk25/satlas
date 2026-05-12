"""Integration tests for /satellites/passes/{cc}.

The endpoint is a thin read-through over Redis populated by the periodic
visits/recompute sweep — no SGP4 or DB on the request path. Tests mock the
cache layer only, matching the pattern in test_satellites_overhead.
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


def test_returns_cached_passes_verbatim(client):
    cached = json.dumps(
        [
            {
                "norad_id": 25544,
                "entry_time": "2026-05-09T12:00:00Z",
                "exit_time": "2026-05-09T12:05:00Z",
            },
            {
                "norad_id": 25544,
                "entry_time": "2026-05-09T13:32:00Z",
                "exit_time": "2026-05-09T13:38:00Z",
            },
        ]
    )
    with patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget:
        mget.return_value = cached
        resp = client.get("/satellites/passes/KR")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["norad_id"] == 25544
    assert body[0]["entry_time"] < body[0]["exit_time"]


def test_empty_array_when_cache_unset(client):
    with patch("app.services.cache.cache_get", new_callable=AsyncMock) as mget:
        mget.return_value = None
        resp = client.get("/satellites/passes/KR")

    assert resp.status_code == 200
    assert resp.json() == []


def test_404_for_unknown_country(client):
    resp = client.get("/satellites/passes/XX")
    assert resp.status_code == 404


def test_country_code_normalized_to_uppercase(client):
    # `kr` should resolve to KR — boundary lookup and cache key both lower→upper.
    seen_keys: list[str] = []

    async def fake_get(key):
        seen_keys.append(key)
        return None

    with patch("app.services.cache.cache_get", side_effect=fake_get):
        resp = client.get("/satellites/passes/kr")

    assert resp.status_code == 200
    assert any("KR" in k for k in seen_keys)
