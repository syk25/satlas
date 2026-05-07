from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.boundaries import load_country_polygons


@pytest.fixture(autouse=True, scope="session")
def boundaries_loaded():
    load_country_polygons()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_overhead_invalid_country(client):
    response = client.get("/satellites/overhead/XX")
    assert response.status_code == 404


def test_overhead_celestrak_unavailable(client):
    with (
        patch(
            "app.routers.satellites.get_latest_tle_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.routers.satellites.fetch_and_store_tle",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("connection failed"),
        ),
    ):
        response = client.get("/satellites/overhead/KR")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
