"""Unit tests for overhead_simulation — ADR-018."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.boundaries import load_country_polygons
from app.services.overhead_simulation import (
    _can_reach_territory,
    _find_entry_exit,
    simulate_overhead_window,
)


@pytest.fixture(autouse=True, scope="session")
def _boundaries():
    load_country_polygons()


# Real-ish TLE strings: ISS (i=51.6, ~400km) and a low-i geosynchronous-ish.
ISS_LINE1 = "1 25544U 98067A   26129.50000000  .00000000  00000-0  00000-0 0  9999"
ISS_LINE2 = "2 25544  51.6406  21.3520 0006703  61.6303  21.5517 15.49327394434245"
LOW_I_LINE2 = "2 41866   2.0000  61.0000 0001000  61.0000  61.0000 15.50000000123456"


class TestCanReachTerritory:
    def test_iss_reaches_korea(self):
        # Korea lat band ~33-39, ISS i=51.6 → easily reaches.
        assert _can_reach_territory(ISS_LINE2, 33.0, 39.0) is True

    def test_low_inclination_misses_high_latitude(self):
        # i=2 sat with LEO altitude can't reach Norway (lat 58-71).
        assert _can_reach_territory(LOW_I_LINE2, 58.0, 71.0) is False

    def test_low_inclination_reaches_equatorial(self):
        # i=2 sat reaches Indonesia (lat -10 to 5).
        assert _can_reach_territory(LOW_I_LINE2, -10.0, 5.0) is True

    def test_malformed_line_is_permissive(self):
        # Unparseable TLE → include rather than silently drop.
        assert _can_reach_territory("garbage", 0.0, 0.0) is True


class TestFindEntryExit:
    def setup_method(self):
        self.now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)

    def _samples(self, pattern: str) -> list[tuple[datetime, bool]]:
        # 'i' = inside, 'o' = outside, one minute apart.
        return [
            (self.now + timedelta(minutes=i), c == "i") for i, c in enumerate(pattern)
        ]

    def test_no_pass_returns_none(self):
        assert _find_entry_exit(self._samples("oooooooo"), self.now) is None

    def test_already_inside_finds_exit(self):
        # Inside at t=0, exits at t=3.
        result = _find_entry_exit(self._samples("iiioooo"), self.now)
        assert result is not None
        entry, exit_t = result
        assert entry == self.now  # entry clamped to request time
        assert exit_t == self.now + timedelta(minutes=3)

    def test_future_entry_finds_pair(self):
        # Outside until t=2, inside 2-4, outside after.
        result = _find_entry_exit(self._samples("ooiiioo"), self.now)
        assert result is not None
        entry, exit_t = result
        assert entry == self.now + timedelta(minutes=2)
        assert exit_t == self.now + timedelta(minutes=5)

    def test_still_inside_at_window_end_clamps_exit(self):
        # Enters at t=2, never exits within window — exit clamped to last sample.
        result = _find_entry_exit(self._samples("ooiiiii"), self.now)
        assert result is not None
        entry, exit_t = result
        assert entry == self.now + timedelta(minutes=2)
        assert exit_t == self.now + timedelta(minutes=6)

    def test_returns_first_pass_only(self):
        # Two passes in window — only the first is returned.
        result = _find_entry_exit(self._samples("oiioiio"), self.now)
        assert result is not None
        entry, exit_t = result
        assert entry == self.now + timedelta(minutes=1)
        assert exit_t == self.now + timedelta(minutes=3)


class TestSimulateOverheadWindow:
    def test_unknown_country_returns_empty(self):
        now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
        assert simulate_overhead_window("XX", [], now) == []

    def test_empty_candidates_returns_empty(self):
        now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
        assert simulate_overhead_window("KR", [], now) == []

    def test_candidate_not_reaching_territory_is_filtered(self):
        # Low-inclination satellite that can't reach Norway's latitude band.
        now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
        candidate = {
            "norad_id": 99999,
            "name": "TEST",
            "lat": 2.0,
            "lon": 10.0,
            "category": None,
            "orbit_class": None,
            "line1": ISS_LINE1,  # line1 isn't checked for reachability
            "line2": LOW_I_LINE2,
        }
        result = simulate_overhead_window("NO", [candidate], now)
        assert result == []
