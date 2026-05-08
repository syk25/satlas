"""24-hour visit-frequency precompute per country (ADR-019).

For each satellite, sample its 24-hour ground track at 60-second intervals,
then map each sample point to a country via a STRtree spatial index. An
"entry event" is counted whenever the territory under the satellite changes
(outside→country, or country-A→country-B). The result is a per-country
table {norad_id → pass_count}.

The expensive sweep runs as a one-shot background task triggered after a
TLE ingest cycle (admin endpoint at /admin/visits/recompute). Per-country
results are written to Redis hashes consumed by the overhead endpoint.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely.geometry import Point
from shapely.strtree import STRtree

from app.services import boundaries
from app.services.cache import cache_hash_set
from app.services.position import get_position

WINDOW_HOURS = 24
SAMPLE_INTERVAL_SECONDS = 60
VISITS_TTL = 14 * 3600  # 12h ingest cadence + 2h grace

logger = logging.getLogger(__name__)


def _visits_key(country_code: str) -> str:
    return f"satlas:visits:24h:{country_code.upper()}"


_strtree_cache: tuple[STRtree, list[str]] | None = None


def _get_strtree() -> tuple[STRtree, list[str]]:
    """Build (or return cached) STRtree of country polygons.

    Boundaries load once at startup and never change at runtime, so a single
    cached tree per process is fine. Returned alongside the parallel list of
    country codes — STRtree returns indices into the input geometry list.
    """
    global _strtree_cache
    if _strtree_cache is None:
        polys = boundaries._country_polygons
        codes = list(polys.keys())
        geoms = [polys[c] for c in codes]
        _strtree_cache = (STRtree(geoms), codes)
    return _strtree_cache


def reset_strtree_cache() -> None:
    """Test hook — allows boundaries reload to take effect."""
    global _strtree_cache
    _strtree_cache = None


def compute_24h_visits(
    satellites: list[dict[str, Any]],
    now: datetime | None = None,
    window_hours: int = WINDOW_HOURS,
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
) -> dict[str, dict[int, int]]:
    """Return {country_code: {norad_id: pass_count}} for the next window.

    Each satellite's ground track is walked once; territory transitions count
    as entries. Five 60-s samples inside the same country count as one pass,
    not five — only outside→country and country→country transitions count.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    tree, codes = _get_strtree()
    n_samples = window_hours * 3600 // sample_interval_seconds

    visits: dict[str, dict[int, int]] = {}

    for sat in satellites:
        norad_id = sat["norad_id"]
        line1 = sat["line1"]
        line2 = sat["line2"]

        prev_country: str | None = None
        for i in range(n_samples):
            t = now + timedelta(seconds=i * sample_interval_seconds)
            pos = get_position(line1, line2, at=t)
            if pos is None:
                continue
            lat, lon, _ = pos

            # `within` flips the relation correctly: the input point is
            # within a country polygon. (`contains` would be the opposite —
            # point containing a polygon — which is always empty.)
            indices = tree.query(Point(lon, lat), predicate="within")
            current_country = codes[int(indices[0])] if len(indices) else None

            if current_country and current_country != prev_country:
                bucket = visits.setdefault(current_country, {})
                bucket[norad_id] = bucket.get(norad_id, 0) + 1

            prev_country = current_country

    return visits


async def store_visits(visits: dict[str, dict[int, int]]) -> int:
    """Write each country's pass-count table to its Redis hash. Returns the
    number of (country, satellite) pairs persisted."""
    total = 0
    for cc, counts in visits.items():
        if not counts:
            continue
        mapping = {str(norad): str(n) for norad, n in counts.items()}
        await cache_hash_set(_visits_key(cc), mapping, ttl=VISITS_TTL)
        total += len(counts)
    return total
