"""Unit tests for visit_frequency — ADR-019."""

from datetime import datetime, timezone

import pytest

from app.services.boundaries import load_country_polygons
from app.services.visit_frequency import (
    _get_strtree,
    compute_24h_visits,
    reset_strtree_cache,
)


@pytest.fixture(autouse=True, scope="session")
def _boundaries():
    load_country_polygons()
    reset_strtree_cache()


# Real ISS-class TLE — high inclination, 24h sweep should yield non-trivial
# visits across many high-latitude territories.
ISS_LINE1 = "1 25544U 98067A   26129.50000000  .00000000  00000-0  00000-0 0  9999"
ISS_LINE2 = "2 25544  51.6406  21.3520 0006703  61.6303  21.5517 15.49327394434245"


class TestStrtree:
    def test_strtree_returns_country_for_inland_point(self):
        # Build STRtree, then verify a known-inland Seoul lookup hits KR.
        from shapely.geometry import Point

        tree, codes = _get_strtree()
        result = tree.query(Point(127.0, 37.5), predicate="within")
        matched = [codes[int(i)] for i in result]
        assert "KR" in matched


class TestCompute24hVisits:
    def setup_method(self):
        self.now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
        self.iss = {"norad_id": 25544, "line1": ISS_LINE1, "line2": ISS_LINE2}

    def test_iss_passes_high_lat_countries(self):
        # ISS at i=51.6 sweeps everything from -52 to +52 lat. RU/CA at high
        # northern lats should each see multiple passes in 24h.
        visits = compute_24h_visits([self.iss], now=self.now)
        assert "RU" in visits
        assert "CA" in visits
        assert visits["RU"][25544] >= 5
        assert visits["CA"][25544] >= 3

    def test_zero_satellites_returns_empty(self):
        assert compute_24h_visits([], now=self.now) == {}

    def test_pass_counted_once_per_entry_not_per_sample(self):
        # A 5-min pass over a country at 60s sample interval has 5 inside
        # samples but should still count as a single pass. Inspect any country
        # with at least one pass: count must be far smaller than total samples.
        visits = compute_24h_visits([self.iss], now=self.now)
        # If samples-not-passes were counted, RU's count would be ~hundreds.
        # The actual count is in the single digits because RU is large but
        # passes are still discrete.
        assert visits["RU"][25544] < 50

    def test_short_window_yields_proportionally_fewer_visits(self):
        # 1h window covers ~2/3 of one orbit — at most a handful of passes.
        short = compute_24h_visits([self.iss], now=self.now, window_hours=1)
        full = compute_24h_visits([self.iss], now=self.now)
        short_total = sum(sum(c.values()) for c in short.values())
        full_total = sum(sum(c.values()) for c in full.values())
        assert short_total < full_total
