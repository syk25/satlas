"""Tests for TLE ingestion: orbit class computation.

NB: `refresh_tle` category-priority coverage was removed because it was
mock-only — the production path uses SQLAlchemy core's
`pg_insert.on_conflict_do_update`, which can't be faithfully simulated
without a real PG. Per ADR-010, DB-touching behaviour belongs in an
integration test against a live database. Tracked as a backlog issue.
"""

from app.models.satellite import OrbitClass
from app.services.tle_ingest import orbit_class_from_tle

# ── Real TLE line2 samples ──────────────────────────────────────────────────
# ISS — LEO ~400 km, e ≈ 0.0007, n ≈ 15.5 rev/day
ISS_L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49815153432729"
# GPS SVN-68 — MEO ~20200 km, e ≈ 0.004, n ≈ 2.0 rev/day
GPS_L2 = "2 44506  55.3014  78.9540 0041008  95.0931 267.1086  2.00562861107827"
# GOES-18 — GEO ~35786 km, e ≈ 0.0001, n ≈ 1.0 rev/day
GEO_L2 = "2 51850   0.0536 282.2380 0000734 155.9427 204.1400  1.00272376028978"
# Molniya-type — HEO, high eccentricity e ≈ 0.74
HEO_L2 = "2 14842  62.9000  40.0000 7400000  90.0000 270.0000  2.00600000000001"


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
