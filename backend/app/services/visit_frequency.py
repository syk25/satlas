"""24-hour pass timeline + per-country pass-count precompute (ADR-019, ADR-024).

For each satellite, sample its 24-hour ground track at 60-second intervals
and map each sample to a country via a STRtree spatial index. Each
outside→country or country-A→country-B transition opens a pass; the next
transition out closes it. The walk produces a timeline of
(country, norad_id, entry_time, exit_time) tuples; pass counts per
(country, norad_id) are aggregated from that timeline.

The expensive sweep runs as a one-shot background task triggered after a
TLE ingest cycle (admin endpoint at /admin/visits/recompute).

ADR-024: the sweep is chunked — `compute_24h_passes_chunk` processes one
batch of satellites and `store_passes_chunk` appends the chunk's events
to Redis (HINCRBY + RPUSH) instead of accumulating the full 16k-satellite
result in memory before writing. Per-country pass lists are stored as
Redis lists; the passes endpoint LRANGEs them on demand.
"""

import json
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely.geometry import Point
from shapely.strtree import STRtree

from app.services import boundaries
from app.services.cache import (
    cache_chunk_apply,
    cache_hash_set,
    cache_pipeline_delete,
    cache_set,
)
from app.services.position import get_position

WINDOW_HOURS = 24
SAMPLE_INTERVAL_SECONDS = 60
VISITS_TTL = 14 * 3600  # 12h ingest cadence + 2h grace
PASSES_TTL = VISITS_TTL  # passes and counts share a lifecycle by design

logger = logging.getLogger(__name__)


def _visits_key(country_code: str) -> str:
    return f"satlas:visits:24h:{country_code.upper()}"


def _passes_key(country_code: str) -> str:
    return f"satlas:passes:24h:{country_code.upper()}"


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


def compute_24h_passes(
    satellites: list[dict[str, Any]],
    now: datetime | None = None,
    window_hours: int = WINDOW_HOURS,
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    """Return {country_code: [{norad_id, entry_time, exit_time}, ...]}.

    NB: this materialises the full result set in memory. Production
    recompute uses the chunked entry point (`admin.recompute_visits` calls
    this per chunk via asyncio.to_thread). The non-chunked signature stays
    for unit tests and any one-off internal caller that knows the input
    is small.

    Each satellite's ground track is walked once. Sample transitions detect
    pass boundaries:
    - outside → country: open a pass at `t`.
    - country-A → country-B: close A at `t`, open B at `t`.
    - country → outside: close at `t`.

    A pass open at the window's end is closed with exit_time = end-of-window.
    GEO satellites that sit permanently over one country produce zero passes
    (no transitions) — Issue #3 tracks a follow-up model for them.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    tree, codes = _get_strtree()
    n_samples = window_hours * 3600 // sample_interval_seconds
    window_end = now + timedelta(hours=window_hours)

    passes: dict[str, list[dict[str, Any]]] = {}

    for sat in satellites:
        norad_id = sat["norad_id"]
        line1 = sat["line1"]
        line2 = sat["line2"]
        # Metadata is propagated into events so the passes endpoint can
        # render a row without a second lookup. Optional via .get() so
        # tests and internal callers can still pass minimal sat dicts.
        name = sat.get("name")
        category = sat.get("category")
        orbit_class = sat.get("orbit_class")

        prev_country: str | None = None
        entry_time: datetime | None = None

        for i in range(n_samples):
            t = now + timedelta(seconds=i * sample_interval_seconds)
            pos = get_position(line1, line2, at=t)
            if pos is None:
                continue
            lat, lon, _ = pos

            indices = tree.query(Point(lon, lat), predicate="within")
            current_country = codes[int(indices[0])] if len(indices) else None

            if current_country != prev_country:
                # Close the previous country's pass.
                if prev_country and entry_time is not None:
                    passes.setdefault(prev_country, []).append(
                        {
                            "norad_id": norad_id,
                            "name": name,
                            "category": category,
                            "orbit_class": orbit_class,
                            "entry_time": entry_time,
                            "exit_time": t,
                        }
                    )
                # Open the new country's pass.
                entry_time = t if current_country else None

            prev_country = current_country

        # Sweep ended while still inside a country: close the pass at the
        # window edge instead of leaving it open. Lets the consumer treat
        # exit_time as authoritative.
        if prev_country and entry_time is not None:
            passes.setdefault(prev_country, []).append(
                {
                    "norad_id": norad_id,
                    "name": name,
                    "category": category,
                    "orbit_class": orbit_class,
                    "entry_time": entry_time,
                    "exit_time": window_end,
                }
            )

    return passes


def aggregate_pass_counts(
    passes: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[int, int]]:
    """Collapse a passes timeline into the {cc: {norad_id: count}} table the
    overhead endpoint reads. Each pass is one entry — equivalent to the
    transition-count behaviour the old `compute_24h_visits` returned."""
    counts: dict[str, dict[int, int]] = {}
    for cc, events in passes.items():
        bucket = counts.setdefault(cc, {})
        for ev in events:
            nid = ev["norad_id"]
            bucket[nid] = bucket.get(nid, 0) + 1
    return counts


async def store_passes(passes: dict[str, list[dict[str, Any]]]) -> tuple[int, int]:
    """Persist the full result set wholesale — kept for the single-batch
    test fixture and any small one-shot caller. Production uses
    `store_passes_chunk` instead (ADR-024).

    Returns (count_pairs_written, country_timelines_written).
    """
    counts = aggregate_pass_counts(passes)
    count_pairs = 0
    for cc, c in counts.items():
        if not c:
            continue
        mapping = {str(nid): str(n) for nid, n in c.items()}
        await cache_hash_set(_visits_key(cc), mapping, ttl=VISITS_TTL)
        count_pairs += len(c)

    timelines_written = 0
    for cc, events in passes.items():
        if not events:
            continue
        serialized = json.dumps([_event_to_dict(ev) for ev in events])
        await cache_set(_passes_key(cc), serialized, ttl=PASSES_TTL)
        timelines_written += 1

    return count_pairs, timelines_written


def _event_to_dict(ev: dict[str, Any]) -> dict[str, Any]:
    """Serialise an event dict to the wire shape (ISO 8601 'Z' timestamps)."""
    return {
        "norad_id": ev["norad_id"],
        "name": ev.get("name"),
        "category": ev.get("category"),
        "orbit_class": ev.get("orbit_class"),
        "entry_time": ev["entry_time"].isoformat().replace("+00:00", "Z"),
        "exit_time": ev["exit_time"].isoformat().replace("+00:00", "Z"),
    }


async def begin_recompute(country_codes: Iterable[str]) -> None:
    """Clear stale `satlas:visits:24h:*` + `satlas:passes:24h:*` keys before
    a chunked sweep starts (ADR-024).

    Per-country writes that follow are incremental (HINCRBY / RPUSH) — without
    a clean slate, stale values from the previous sweep would compound into
    inflated counts. The window of brief emptiness during recompute is
    acceptable: the GHA cron is the only writer, and the dashboard/passes UI
    both already handle empty results gracefully.
    """
    keys: list[str] = []
    for cc in country_codes:
        keys.append(_visits_key(cc))
        keys.append(_passes_key(cc))
    await cache_pipeline_delete(keys)


async def store_passes_chunk(
    chunk_passes: dict[str, list[dict[str, Any]]],
) -> tuple[int, int]:
    """Append one chunk's events to Redis (ADR-024). Visits hash is updated
    via HINCRBY per (cc, norad_id), passes list via RPUSH; both keys' TTLs
    are refreshed in the same pipeline.

    Returns (count_pairs_in_chunk, events_in_chunk) — totals are summed by
    the caller across chunks for reporting.
    """
    if not chunk_passes:
        return 0, 0

    visits_updates: dict[str, dict[str, int]] = {}
    passes_appends: dict[str, list[str]] = {}
    pairs = 0
    events_total = 0

    for cc, events in chunk_passes.items():
        if not events:
            continue
        visits_key = _visits_key(cc)
        passes_key = _passes_key(cc)
        counts = visits_updates.setdefault(visits_key, {})
        encoded_list = passes_appends.setdefault(passes_key, [])
        for ev in events:
            nid = str(ev["norad_id"])
            counts[nid] = counts.get(nid, 0) + 1
            encoded_list.append(json.dumps(_event_to_dict(ev)))
            events_total += 1
        pairs += len(counts)

    await cache_chunk_apply(
        visits_updates,
        passes_appends,
        visits_ttl=VISITS_TTL,
        passes_ttl=PASSES_TTL,
    )

    return pairs, events_total
