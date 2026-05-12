"""Unit tests for visit_frequency — ADR-019 + pass timeline extension."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.boundaries import load_country_polygons
from app.services.visit_frequency import (
    _get_strtree,
    aggregate_pass_counts,
    compute_24h_passes,
    reset_strtree_cache,
)


@pytest.fixture(autouse=True, scope="session")
def _boundaries():
    load_country_polygons()
    reset_strtree_cache()


# Real ISS-class TLE — high inclination, 24h sweep should yield non-trivial
# passes across many high-latitude territories.
ISS_LINE1 = "1 25544U 98067A   26129.50000000  .00000000  00000-0  00000-0 0  9999"
ISS_LINE2 = "2 25544  51.6406  21.3520 0006703  61.6303  21.5517 15.49327394434245"


class TestStrtree:
    def test_strtree_returns_country_for_inland_point(self):
        from shapely.geometry import Point

        tree, codes = _get_strtree()
        result = tree.query(Point(127.0, 37.5), predicate="within")
        matched = [codes[int(i)] for i in result]
        assert "KR" in matched


class TestCompute24hPasses:
    def setup_method(self):
        self.now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
        self.iss = {"norad_id": 25544, "line1": ISS_LINE1, "line2": ISS_LINE2}

    def test_iss_passes_high_lat_countries(self):
        # ISS at i=51.6 sweeps everything from -52 to +52 lat. RU/CA at high
        # northern lats should each see multiple passes in 24h.
        passes = compute_24h_passes([self.iss], now=self.now)
        assert "RU" in passes
        assert "CA" in passes
        counts = aggregate_pass_counts(passes)
        assert counts["RU"][25544] >= 5
        assert counts["CA"][25544] >= 3

    def test_zero_satellites_returns_empty(self):
        assert compute_24h_passes([], now=self.now) == {}

    def test_pass_counted_once_per_entry_not_per_sample(self):
        # A 5-min pass at 60s sample interval has 5 inside samples but is
        # still one pass. Count must be far smaller than total samples.
        counts = aggregate_pass_counts(compute_24h_passes([self.iss], now=self.now))
        assert counts["RU"][25544] < 50

    def test_short_window_yields_proportionally_fewer_passes(self):
        short = compute_24h_passes([self.iss], now=self.now, window_hours=1)
        full = compute_24h_passes([self.iss], now=self.now)
        short_total = sum(len(events) for events in short.values())
        full_total = sum(len(events) for events in full.values())
        assert short_total < full_total

    def test_each_pass_has_entry_before_exit_within_window(self):
        window_hours = 24
        window_end = self.now + timedelta(hours=window_hours)
        passes = compute_24h_passes([self.iss], now=self.now, window_hours=window_hours)
        # Inspect every event — entry < exit, both inside the window.
        for events in passes.values():
            for ev in events:
                assert ev["norad_id"] == 25544
                assert ev["entry_time"] < ev["exit_time"]
                assert self.now <= ev["entry_time"] <= window_end
                assert self.now <= ev["exit_time"] <= window_end

    def test_aggregate_counts_match_event_lengths(self):
        # Counts should be exactly the number of events per (cc, norad_id).
        passes = compute_24h_passes([self.iss], now=self.now)
        counts = aggregate_pass_counts(passes)
        for cc, events in passes.items():
            assert counts[cc][25544] == sum(1 for e in events if e["norad_id"] == 25544)
