"""Forward-window simulation for overhead satellite membership.

Given the current snapshot of all satellite positions plus their TLE strings,
for each candidate satellite this module determines whether it is currently
over the territory or will enter within the next N minutes, and produces
(entry_time, exit_time) per ADR-018.

The simulation runs in a thread (CPU-bound SGP4 propagation). Results are
cached at the router layer.
"""

import math
from datetime import datetime, timedelta
from typing import Any

from sgp4.api import Satrec, jday

from app.services import boundaries
from app.services.position import _eci_to_geodetic

WINDOW_MINUTES = 30
# 90s (was 60s in ADR-018) — see ADR-020. Cuts SGP4 calls per request by ~33%.
# Entry/exit timing accuracy degrades from ±30s to ±45s, hidden by 1Hz client gating.
SAMPLE_INTERVAL_SECONDS = 90

_EARTH_RADIUS_KM = 6371.0
_MU_KM3_S2 = 398600.4418


def _propagate(line1: str, line2: str, at: datetime) -> tuple[float, float] | None:
    sat = Satrec.twoline2rv(line1, line2)
    sec = at.second + at.microsecond / 1_000_000.0
    jd, fr = jday(at.year, at.month, at.day, at.hour, at.minute, sec)
    error, r, _ = sat.sgp4(jd, fr)
    if error != 0:
        return None
    lat, lon, _ = _eci_to_geodetic(r, at)
    return lat, lon


def _can_reach_territory(line2: str, lat_min: float, lat_max: float) -> bool:
    """Pre-filter: can this satellite's footprint ever reach the territory's
    latitude band, given orbital inclination + footprint radius?

    Cheap (microseconds) — eliminates equatorial satellites for high-lat
    territories and polar satellites for low-lat territories without SGP4.
    """
    try:
        inclination_deg = float(line2[8:16].strip())
        mean_motion = float(line2[52:63].strip())  # rev/day
        n_rad_s = mean_motion * 2 * math.pi / 86400.0
        a_km = (_MU_KM3_S2 / n_rad_s**2) ** (1.0 / 3.0)
        alt_km = max(a_km - _EARTH_RADIUS_KM, 0.0)
    except (ValueError, ZeroDivisionError, IndexError):
        return True  # be permissive when TLE parse fails

    if alt_km < 1:
        return False

    cos_phi = _EARTH_RADIUS_KM / (_EARTH_RADIUS_KM + alt_km)
    cos_phi = max(min(cos_phi, 1.0), -1.0)
    footprint_deg = math.degrees(math.acos(cos_phi))

    # Retrograde orbits (i > 90) cover the same |lat| band as 180 - i prograde.
    effective_inc = inclination_deg if inclination_deg <= 90 else 180 - inclination_deg
    max_lat = min(effective_inc + footprint_deg, 90.0)
    return not (lat_max < -max_lat or lat_min > max_lat)


def _find_entry_exit(
    samples: list[tuple[datetime, bool]],
    request_time: datetime,
) -> tuple[datetime, datetime] | None:
    """Walk the samples and pull the first (entry, exit) pair.

    If the first sample is already inside, entry = request_time (we don't look
    backward — the satellite is visible right now and the gating only checks
    now ∈ [entry, exit] going forward).
    """
    if not samples:
        return None

    if samples[0][1]:
        entry = request_time
        for t, inside in samples[1:]:
            if not inside:
                return entry, t
        # Still inside at window end — exit_time clamped to window end.
        return entry, samples[-1][0]

    # First sample outside: find first outside→inside transition.
    for i in range(1, len(samples)):
        if samples[i][1] and not samples[i - 1][1]:
            entry = samples[i][0]
            for j in range(i + 1, len(samples)):
                if not samples[j][1]:
                    return entry, samples[j][0]
            return entry, samples[-1][0]
    return None


def simulate_overhead_window(
    country_code: str,
    candidates: list[dict[str, Any]],
    now: datetime,
    window_minutes: int = WINDOW_MINUTES,
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
) -> list[dict[str, Any]]:
    """Return candidates currently over `country_code` or entering within the
    window, annotated with `entry_time` and `exit_time` (datetime).

    `candidates` is the already-filtered position snapshot (each dict has
    norad_id, name, lat, lon, line1, line2, plus the metadata fields the
    overhead endpoint surfaces).
    """
    cc = country_code.upper()
    territory = boundaries._country_polygons.get(cc)
    if territory is None:
        return []

    minx, miny, maxx, maxy = territory.bounds  # (lon_min, lat_min, lon_max, lat_max)
    n_extra_samples = window_minutes * 60 // sample_interval_seconds

    results: list[dict[str, Any]] = []

    for sat in candidates:
        line2 = sat["line2"]
        if not _can_reach_territory(line2, miny, maxy):
            continue

        line1 = sat["line1"]
        # Reuse the t=0 lat/lon already computed by the snapshot job —
        # avoids one redundant SGP4 call per satellite.
        first_inside = boundaries.is_over_country(sat["lat"], sat["lon"], cc)
        samples: list[tuple[datetime, bool]] = [(now, first_inside)]

        for i in range(1, n_extra_samples + 1):
            t = now + timedelta(seconds=i * sample_interval_seconds)
            pos = _propagate(line1, line2, t)
            if pos is None:
                samples.append((t, False))
                continue
            lat, lon = pos
            samples.append((t, boundaries.is_over_country(lat, lon, cc)))

        pair = _find_entry_exit(samples, now)
        if pair is None:
            continue

        entry, exit_t = pair
        results.append({**sat, "entry_time": entry, "exit_time": exit_t})

    return results


def compute_window_positions(
    candidates: list[dict[str, Any]],
    now: datetime,
    window_minutes: int = WINDOW_MINUTES,
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
) -> list[dict[str, Any]]:
    """Propagate each candidate at every sample time once.

    The per-country `simulate_overhead_window` propagates the same satellite at
    the same sample times for every country. When the prewarm sweep runs across
    200 territories that means ~200× redundant SGP4 work. Hoisting the
    propagation out lets the sweep do it once and have each country pay only
    the polygon-containment cost.

    Returns the candidate dicts with an extra `samples` key:
    `[(t0, lat0, lon0), (t1, lat1, lon1), ...]` where t0 == now.
    """
    n_extra_samples = window_minutes * 60 // sample_interval_seconds
    sample_times = [
        now + timedelta(seconds=i * sample_interval_seconds)
        for i in range(n_extra_samples + 1)
    ]

    enriched: list[dict[str, Any]] = []
    for sat in candidates:
        line1 = sat["line1"]
        line2 = sat["line2"]
        # Reuse the t=0 snapshot lat/lon — saves one SGP4 call per satellite.
        samples: list[tuple[datetime, float, float] | tuple[datetime, None, None]] = [
            (now, sat["lat"], sat["lon"])
        ]
        for t in sample_times[1:]:
            pos = _propagate(line1, line2, t)
            if pos is None:
                samples.append((t, None, None))
            else:
                samples.append((t, pos[0], pos[1]))
        enriched.append({**sat, "samples": samples})
    return enriched


def find_overhead_in_window(
    country_code: str,
    window_positions: list[dict[str, Any]],
    request_time: datetime,
) -> list[dict[str, Any]]:
    """Polygon-only pass over already-propagated positions.

    Counterpart to `compute_window_positions` — same output shape as
    `simulate_overhead_window` but no SGP4 inside.
    """
    cc = country_code.upper()
    territory = boundaries._country_polygons.get(cc)
    if territory is None:
        return []

    _, miny, _, maxy = territory.bounds

    results: list[dict[str, Any]] = []
    for sat in window_positions:
        if not _can_reach_territory(sat["line2"], miny, maxy):
            continue

        samples_inside: list[tuple[datetime, bool]] = []
        for t, lat, lon in sat["samples"]:
            if lat is None or lon is None:
                samples_inside.append((t, False))
            else:
                samples_inside.append((t, boundaries.is_over_country(lat, lon, cc)))

        pair = _find_entry_exit(samples_inside, request_time)
        if pair is None:
            continue

        entry, exit_t = pair
        # Strip the heavy `samples` field before yielding the result.
        sat_out = {k: v for k, v in sat.items() if k != "samples"}
        results.append({**sat_out, "entry_time": entry, "exit_time": exit_t})

    return results
