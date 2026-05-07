import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.boundaries import load_country_polygons


@pytest.fixture(autouse=True, scope="session")
def boundaries_loaded():
    load_country_polygons()


@pytest.fixture
def client():
    with (
        patch("app.main.refresh_tle", new_callable=AsyncMock),
        patch("app.main.start_scheduler"),
        patch("app.main.stop_scheduler"),
    ):
        with TestClient(app) as c:
            yield c


def test_overhead_invalid_country(client):
    response = client.get("/satellites/overhead/XX")
    assert response.status_code == 404


def test_overhead_no_tle_data(client):
    """503 when DB has no TLE data (e.g. CelesTrak was down at startup)."""
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
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 503
    assert "not yet available" in response.json()["detail"].lower()


def test_overhead_cache_hit_skips_db(client):
    tle1 = "1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9999"
    tle2 = "2 25544  51.6400 000.0000 0000001   0.0000   0.0000 15.50000000000000"
    cached_satellite = {
        "norad_id": 25544,
        "name": "ISS (ZARYA)",
        "operator_country": "US",
        "operator_name": None,
        "operator_type": None,
        "orbit_class": None,
        "line1": tle1,
        "line2": tle2,
        "entry_time": datetime.now(timezone.utc).isoformat(),
    }

    with (
        patch(
            "app.routers.satellites.cache.cache_get",
            new_callable=AsyncMock,
            return_value=json.dumps([cached_satellite]),
        ),
        patch(
            "app.routers.satellites.get_latest_tle_snapshots",
            new_callable=AsyncMock,
        ) as mock_db,
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["norad_id"] == 25544
    mock_db.assert_not_called()
