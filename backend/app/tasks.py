"""Celery task definitions (ADR-021).

Each task is a thin wrapper that runs an async coroutine via asyncio.run.
Redis connections are opened per-task and closed at the end so we don't
leak handles across event loops.
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
    """Recompute /overhead default-case caches for every loaded country.

    Identical effect to the in-process job that ADR-020 first introduced;
    moved here per ADR-021 so the work cannot starve API request workers.
    """
    return asyncio.run(_run_prewarm())


async def _run_prewarm() -> dict[str, Any]:
    # Imports inside the function so the worker boot doesn't pay for FastAPI's
    # router-construction side effects until the first task runs.
    from app.routers.satellites import OVERHEAD_CACHE_TTL, SatelliteOverhead
    from app.services import boundaries, cache
    from app.services.overhead_simulation import simulate_overhead_window
    from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY
    from app.services.visit_frequency import _visits_key

    await cache.init_redis()
    try:
        all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
        if all_json is None:
            logger.warning("prewarm: positions cache empty, skipping cycle")
            return {"skipped": True}

        all_positions = json.loads(all_json)
        payload_only = [
            p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
        ]
        countries = list(boundaries._country_polygons.keys())
        now = datetime.now(timezone.utc)

        t0 = time.time()
        total_rows = 0
        failed: list[str] = []

        for cc in countries:
            try:
                windowed = simulate_overhead_window(cc, payload_only, now)

                norad_fields = [str(p["norad_id"]) for p in windowed]
                pass_counts_raw = await cache.cache_hash_mget(
                    _visits_key(cc), norad_fields
                )
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
                total_rows += len(result)
            except Exception:
                logger.exception("prewarm failed for %s", cc)
                failed.append(cc)

        elapsed = time.time() - t0
        logger.info(
            "prewarm cycle done: %d/%d countries, %d rows, %.1fs",
            len(countries) - len(failed),
            len(countries),
            total_rows,
            elapsed,
        )
        return {
            "countries_ok": len(countries) - len(failed),
            "countries_total": len(countries),
            "rows": total_rows,
            "elapsed_seconds": round(elapsed, 1),
            "failed": failed,
        }
    finally:
        await cache.close_redis()
