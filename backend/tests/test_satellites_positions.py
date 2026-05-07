import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with (
        patch("app.main.refresh_tle", new_callable=AsyncMock),
        patch("app.main.start_scheduler"),
        patch("app.main.stop_scheduler"),
    ):
        with TestClient(app) as c:
            yield c


def _make_row(norad_id: int, name: str, line1: str, line2: str):
    satellite = MagicMock()
    satellite.norad_id = norad_id
    satellite.name = name
    satellite.is_active = True

    snapshot = MagicMock()
    snapshot.line1 = line1
    snapshot.line2 = line2

    return (satellite, snapshot)


ISS_LINE1 = "1 25544U 98067A   24001.50000000  .00001764  00000-0  40811-4 0  9994"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49815153432729"


def test_positions_no_tle_data(client):
    """503 when DB has no TLE snapshots."""
    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.routers.satellites.get_latest_tle_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        response = client.get("/satellites/positions")

    assert response.status_code == 503
    assert "not yet available" in response.json()["detail"].lower()


def test_positions_cache_hit_skips_db(client):
    """Cache hit returns data without touching the DB."""
    cached = [{"norad_id": 25544, "name": "ISS (ZARYA)", "lat": 10.0, "lon": 20.0}]

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            new_callable=AsyncMock,
            return_value=json.dumps(cached),
        ),
        patch(
            "app.routers.satellites.get_latest_tle_snapshots",
            new_callable=AsyncMock,
        ) as mock_db,
    ):
        response = client.get("/satellites/positions")

    assert response.status_code == 200
    assert response.json()[0]["norad_id"] == 25544
    mock_db.assert_not_called()


def test_positions_returns_lat_lon(client):
    """Valid TLE produces lat/lon within bounds."""
    row = _make_row(25544, "ISS (ZARYA)", ISS_LINE1, ISS_LINE2)

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.routers.satellites.get_latest_tle_snapshots",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.routers.satellites.cache.cache_set",
            new_callable=AsyncMock,
        ),
    ):
        response = client.get("/satellites/positions")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    sat = data[0]
    assert sat["norad_id"] == 25544
    assert -90 <= sat["lat"] <= 90
    assert -180 <= sat["lon"] <= 180
