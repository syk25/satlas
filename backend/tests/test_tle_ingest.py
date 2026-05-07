"""Tests for TLE ingestion: orbit class computation and category priority."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.satellite import OrbitClass, SatelliteCategory
from app.services.tle_ingest import orbit_class_from_tle, refresh_tle

# ── Real TLE line2 samples ──────────────────────────────────────────────────
# ISS — LEO ~400 km, e ≈ 0.0007, n ≈ 15.5 rev/day
ISS_L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49815153432729"
# GPS SVN-68 — MEO ~20200 km, e ≈ 0.004, n ≈ 2.0 rev/day
GPS_L2 = "2 44506  55.3014  78.9540 0041008  95.0931 267.1086  2.00562861107827"
# GOES-18 — GEO ~35786 km, e ≈ 0.0001, n ≈ 1.0 rev/day
GEO_L2 = "2 51850   0.0536 282.2380 0000734 155.9427 204.1400  1.00272376028978"
# Molniya-type — HEO, high eccentricity e ≈ 0.74
HEO_L2 = "2 14842  62.9000  40.0000 7400000  90.0000 270.0000  2.00600000000001"


# ── orbit_class_from_tle ────────────────────────────────────────────────────


class TestOrbitClassFromTle:
    def test_iss_is_leo(self):
        assert orbit_class_from_tle(ISS_L2) == OrbitClass.LEO

    def test_gps_is_meo(self):
        assert orbit_class_from_tle(GPS_L2) == OrbitClass.MEO

    def test_geo_satellite(self):
        assert orbit_class_from_tle(GEO_L2) == OrbitClass.GEO

    def test_high_eccentricity_is_heo(self):
        assert orbit_class_from_tle(HEO_L2) == OrbitClass.HEO

    def test_malformed_line_defaults_to_leo(self):
        assert orbit_class_from_tle("2 99999  garbage data here") == OrbitClass.LEO


# ── refresh_tle category priority ───────────────────────────────────────────

ISS_NAME = "ISS (ZARYA)"
ISS_L1 = "1 25544U 98067A   24001.50000000  .00001764  00000-0  40811-4 0  9994"

STATION_BLOCK = f"{ISS_NAME}\n{ISS_L1}\n{ISS_L2}\n"
ACTIVE_BLOCK = f"{ISS_NAME}\n{ISS_L1}\n{ISS_L2}\n"


def _mock_response(text: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


@pytest.mark.asyncio
async def test_specific_category_beats_other():
    """A satellite seen in `stations` keeps STATION even when `active` runs later."""
    stored: dict = {}

    async def fake_execute(stmt):
        result = MagicMock()
        norad_id = 25544
        if norad_id in stored:
            sat = stored[norad_id]
            result.scalar_one_or_none.return_value = sat
        else:
            result.scalar_one_or_none.return_value = None
        return result

    async def fake_flush():
        # Simulate the satellite being saved after first flush
        if 25544 not in stored:
            # Grab the satellite that was just add()ed
            sat = last_added[0]
            sat.id = 1
            stored[25544] = sat

    last_added = []

    class FakeDb:
        async def execute(self, stmt):
            return await fake_execute(stmt)

        async def flush(self):
            await fake_flush()

        async def commit(self):
            pass

        def add(self, obj):
            if hasattr(obj, "norad_id"):
                last_added.clear()
                last_added.append(obj)

    responses = {
        "stations": STATION_BLOCK,
    }
    # All other feeds return empty
    default_response = _mock_response("")

    async def fake_get(url, **kwargs):
        for group, body in responses.items():
            if group in url:
                return _mock_response(body)
        return default_response

    with patch("app.services.tle_ingest.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await refresh_tle(FakeDb())

    # Satellite created by stations feed must have STATION category
    assert stored[25544].category == SatelliteCategory.STATION


@pytest.mark.asyncio
async def test_other_does_not_overwrite_specific_category():
    """active feed (OTHER) must not downgrade an already-categorised satellite."""
    from app.models.satellite import Satellite

    existing_sat = MagicMock(spec=Satellite)
    existing_sat.norad_id = 25544
    existing_sat.id = 1
    existing_sat.category = SatelliteCategory.STATION  # already set
    existing_sat.orbit_class = OrbitClass.LEO

    async def fake_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_sat
        return result

    class FakeDb:
        async def execute(self, stmt):
            return await fake_execute(stmt)

        async def flush(self):
            pass

        async def commit(self):
            pass

        def add(self, obj):
            pass

    async def fake_get(url, **kwargs):
        if "active" in url:
            return _mock_response(ACTIVE_BLOCK)
        return _mock_response("")

    with patch("app.services.tle_ingest.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await refresh_tle(FakeDb())

    # Category must remain STATION, not be downgraded to OTHER
    assert existing_sat.category == SatelliteCategory.STATION
