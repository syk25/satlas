import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import AsyncSessionLocal
from app.services import boundaries, cache
from app.services.cache import cache_clear_pattern
from app.services.overhead_simulation import simulate_overhead_window
from app.services.tle_ingest import (
    POSITIONS_ALL_CACHE_KEY,
    refresh_tle,
    warm_positions_cache,
)
from app.services.visit_frequency import _visits_key

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="UTC")


async def refresh_tle_job() -> None:
    logger.info("TLE refresh started")
    async with AsyncSessionLocal() as db:
        try:
            count = await refresh_tle(db)
        except Exception:
            logger.exception("TLE refresh failed")
            return

    if count > 0:
        # Glob clears all derived position caches (`:full`, future variants)
        # AND the master `:all` cache; warm_positions_cache rebuilds master.
        await cache_clear_pattern("satlas:overhead:*")
        await cache_clear_pattern("satlas:positions*")
        async with AsyncSessionLocal() as warm_db:
            await warm_positions_cache(warm_db)

    logger.info("TLE refresh complete, processed %d snapshots", count)


async def warm_positions_job() -> None:
    logger.info("positions cache warming started")
    async with AsyncSessionLocal() as db:
        try:
            count = await warm_positions_cache(db)
        except Exception:
            logger.exception("positions cache warming failed")
            return
    logger.info("positions cache warming complete: %d satellites", count)


async def prewarm_overhead_job() -> None:
    """Prewarm the default-case /overhead cache for every loaded country.

    ADR-020: ensures interactive clicks always hit a warm cache. Iterates
    countries serially in a worker thread to avoid stalling the event loop;
    the per-country simulation is fast enough (~1 s on 2 vCPU after the
    boundary fast-path) that 200 countries fit well under the 15 min cycle.
    """
    from app.routers.satellites import OVERHEAD_CACHE_TTL, SatelliteOverhead

    logger.info("overhead prewarm started")
    t0 = time.time()

    all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
    if all_json is None:
        logger.warning("overhead prewarm: positions cache not warm yet, skipping")
        return

    all_positions = json.loads(all_json)
    payload_only = [
        p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
    ]
    countries = list(boundaries._country_polygons.keys())
    now = datetime.now(timezone.utc)

    total_rows = 0
    failed: list[str] = []

    for cc in countries:
        try:
            windowed = await asyncio.to_thread(
                simulate_overhead_window, cc, payload_only, now
            )

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
            total_rows += len(result)
        except Exception:
            logger.exception("overhead prewarm failed for %s", cc)
            failed.append(cc)

    elapsed = time.time() - t0
    logger.info(
        "overhead prewarm complete: %d countries, %d rows, %.1fs%s",
        len(countries) - len(failed),
        total_rows,
        elapsed,
        f", {len(failed)} failed" if failed else "",
    )
    if elapsed > 600:
        logger.warning("overhead prewarm exceeded 10 minutes: %.1fs", elapsed)


def start_scheduler(seed_immediately: bool = False) -> None:
    _scheduler.add_job(
        refresh_tle_job, CronTrigger(hour=0, minute=0), id="tle_refresh_0000"
    )
    _scheduler.add_job(
        refresh_tle_job, CronTrigger(hour=12, minute=0), id="tle_refresh_1200"
    )
    _scheduler.add_job(
        warm_positions_job, IntervalTrigger(seconds=60), id="warm_positions"
    )
    # ADR-020: keep every country's /overhead default-case cache warm.
    _scheduler.add_job(
        prewarm_overhead_job, IntervalTrigger(minutes=15), id="prewarm_overhead"
    )
    if seed_immediately:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        _scheduler.add_job(refresh_tle_job, DateTrigger(run_date=run_at), id="tle_seed")
    # warm positions immediately on startup (10s delay so DB connection settles)
    boot_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    _scheduler.add_job(
        warm_positions_job, DateTrigger(run_date=boot_at), id="warm_positions_boot"
    )
    # First prewarm runs 30s after boot — gives warm_positions_job time to
    # populate POSITIONS_ALL_CACHE_KEY first.
    prewarm_boot_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    _scheduler.add_job(
        prewarm_overhead_job,
        DateTrigger(run_date=prewarm_boot_at),
        id="prewarm_overhead_boot",
    )
    _scheduler.start()


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
