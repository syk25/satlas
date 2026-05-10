"""Celery task definitions (ADR-021 + 022).

The prewarm sweep started life as a single task, was split into a per-country
fan-out when sequential SGP4 work blew the time budget, and is now collapsed
back to a single task because the SGP4 redundancy that made fan-out necessary
no longer exists: window positions are propagated once for all satellites and
each country pays only the polygon-containment cost on top.

Per-task structure: import-inside-the-function so that loading this module
doesn't pull in the FastAPI router at worker boot, and a fresh Redis client
per asyncio.run so we don't leak connections across event loops.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.prewarm_overhead_all_countries")
def prewarm_overhead_all_countries() -> dict[str, Any]:
    """Beat-fired sweep: propagate every satellite once across the window,
    then for each country reuse those positions for a polygon-only pass and
    write the per-country cache.
    """
    return asyncio.run(_run_sweep())


async def _run_sweep() -> dict[str, Any]:
    from app.routers.satellites import OVERHEAD_CACHE_TTL, SatelliteOverhead
    from app.services import boundaries, cache
    from app.services.overhead_simulation import (
        compute_window_positions,
        find_overhead_in_window,
    )
    from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY
    from app.services.visit_frequency import _visits_key

    if not boundaries._country_polygons:
        boundaries.load_country_polygons()

    await cache.init_redis()
    try:
        all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
        if all_json is None:
            return {"skipped": True, "reason": "positions cache empty"}

        all_positions = json.loads(all_json)
        payload_only = [
            p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
        ]

        sweep_start = time.time()
        now = datetime.now(timezone.utc)

        propagation_start = time.time()
        window_positions = compute_window_positions(payload_only, now)
        propagation_elapsed = time.time() - propagation_start

        countries = list(boundaries._country_polygons.keys())
        per_country_elapsed: list[float] = []

        for cc in countries:
            t0 = time.time()
            windowed = find_overhead_in_window(cc, window_positions, now)

            norad_fields = [str(p["norad_id"]) for p in windowed]
            pass_counts_raw = await cache.cache_hash_mget(_visits_key(cc), norad_fields)
            pass_counts: list[int | None] = [
                int(v) if v is not None else None for v in pass_counts_raw
            ]

            result = [
                SatelliteOverhead(
                    norad_id=p["norad_id"],
                    name=p["name"],
                    category=p["category"],
                    operator=p.get("operator"),
                    operator_name=None,
                    operator_type=None,
                    orbit_class=p["orbit_class"],
                    launch_date=p.get("launch_date"),
                    decay_date=p.get("decay_date"),
                    international_designator=p.get("international_designator"),
                    object_type=p.get("object_type"),
                    rcs_size=p.get("rcs_size"),
                    line1=p["line1"],
                    line2=p["line2"],
                    entry_time=p["entry_time"],
                    exit_time=p["exit_time"],
                    passes_24h=pass_counts[i],
                )
                for i, p in enumerate(windowed)
            ]

            await cache.cache_set(
                f"satlas:overhead:{cc.upper()}",
                json.dumps([item.model_dump(mode="json") for item in result]),
                ttl=OVERHEAD_CACHE_TTL,
            )
            per_country_elapsed.append(time.time() - t0)

        total_elapsed = time.time() - sweep_start
        logger.info(
            "prewarm sweep complete: %d countries in %.2fs "
            "(propagation %.2fs, polygon+cache %.2fs total)",
            len(countries),
            total_elapsed,
            propagation_elapsed,
            sum(per_country_elapsed),
        )
        return {
            "countries": len(countries),
            "candidates": len(payload_only),
            "propagation_elapsed": round(propagation_elapsed, 2),
            "total_elapsed": round(total_elapsed, 2),
        }
    finally:
        await cache.close_redis()
