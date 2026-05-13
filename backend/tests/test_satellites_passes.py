"""Integration tests for /satellites/passes/{cc}.

The endpoint is a thin read-through over Redis populated by the periodic
visits/recompute sweep — no SGP4 or DB on the request path. ADR-024 moved
the storage from a single JSON blob (cache_get) to a list of JSON-encoded
events (cache_list_range), so the tests mock the new list-range helper.
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


def test_returns_passes_verbatim_from_list(client):
    """Each list element is already a JSON-encoded event; the endpoint
    concatenates them into a JSON array without re-parsing."""
    elements = [
        json.dumps(
            {
                "norad_id": 25544,
                "name": "ISS (ZARYA)",
                "category": "STATION",
                "orbit_class": "LEO",
                "entry_time": "2026-05-09T12:00:00Z",
                "exit_time": "2026-05-09T12:05:00Z",
            }
        ),
        json.dumps(
            {
                "norad_id": 25544,
                "name": "ISS (ZARYA)",
                "category": "STATION",
                "orbit_class": "LEO",
                "entry_time": "2026-05-09T13:32:00Z",
                "exit_time": "2026-05-09T13:38:00Z",
            }
        ),
    ]
    with patch("app.services.cache.cache_list_range", new_callable=AsyncMock) as mrange:
        mrange.return_value = elements
        resp = client.get("/satellites/passes/KR")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["norad_id"] == 25544
    assert body[0]["entry_time"] < body[0]["exit_time"]
    assert body[1]["name"] == "ISS (ZARYA)"


def test_empty_array_when_list_empty(client):
    with patch("app.services.cache.cache_list_range", new_callable=AsyncMock) as mrange:
        mrange.return_value = []
        resp = client.get("/satellites/passes/KR")

    assert resp.status_code == 200
    assert resp.json() == []


def test_404_for_unknown_country(client):
    resp = client.get("/satellites/passes/XX")
    assert resp.status_code == 404


def test_country_code_normalized_to_uppercase(client):
    # `kr` should resolve to KR — boundary lookup and cache key both lower→upper.
    seen_keys: list[str] = []

    async def fake_range(key, start=0, end=-1):
        seen_keys.append(key)
        return []

    with patch("app.services.cache.cache_list_range", side_effect=fake_range):
        resp = client.get("/satellites/passes/kr")

    assert resp.status_code == 200
    assert any("KR" in k for k in seen_keys)
