"""Celery task definitions (ADR-021).

Fan-out pattern: the beat-fired task is just a dispatcher. The real work
lives in `prewarm_overhead_one_country`, which is short enough that
workers can process many in parallel without bumping into the task time
limit. Failures stay scoped to a single country.

Each per-country task runs an async coroutine via asyncio.run; Redis
connections are opened per-task and closed at the end so we don't leak
handles across event loops.
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
    """Beat-fired dispatcher: emits one per-country task for every loaded
    country and returns immediately. Heavy work is in the per-country task.
    """
    from app.services import boundaries

    if not boundaries._country_polygons:
        boundaries.load_country_polygons()

    countries = list(boundaries._country_polygons.keys())
    for cc in countries:
        prewarm_overhead_one_country.delay(cc)

    logger.info("prewarm fanout: dispatched %d per-country tasks", len(countries))
    return {"countries_dispatched": len(countries)}


@celery_app.task(name="app.tasks.prewarm_overhead_one_country")
def prewarm_overhead_one_country(cc: str) -> dict[str, Any]:
    """Run the /overhead default-case simulation for one country and write
    the resulting payload to its cache key."""
    return asyncio.run(_run_one(cc))


async def _run_one(cc: str) -> dict[str, Any]:
    # Imports are inside the function so importing the task module doesn't
    # drag in FastAPI's router-construction side effects until first run.
    from app.routers.satellites import OVERHEAD_CACHE_TTL, SatelliteOverhead
    from app.services import boundaries, cache
    from app.services.overhead_simulation import simulate_overhead_window
    from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY
    from app.services.visit_frequency import _visits_key

    if not boundaries._country_polygons:
        boundaries.load_country_polygons()

    await cache.init_redis()
    try:
        all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
        if all_json is None:
            return {"cc": cc, "skipped": True, "reason": "positions cache empty"}

        all_positions = json.loads(all_json)
        payload_only = [
            p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
        ]

        t0 = time.time()
        now = datetime.now(timezone.utc)
        windowed = simulate_overhead_window(cc, payload_only, now)

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

        cache_key = f"satlas:overhead:{cc.upper()}"
        await cache.cache_set(
            cache_key,
            json.dumps([item.model_dump(mode="json") for item in result]),
            ttl=OVERHEAD_CACHE_TTL,
        )
        elapsed = time.time() - t0
        return {"cc": cc, "rows": len(result), "elapsed": round(elapsed, 2)}
    finally:
        await cache.close_redis()
