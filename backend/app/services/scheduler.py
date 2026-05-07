import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import AsyncSessionLocal
from app.services.cache import cache_clear_pattern
from app.services.tle_ingest import (
    CELESTRAK_STATIONS_URL,
    CELESTRAK_URL,
    fetch_and_store_tle,
    get_latest_tle_snapshots,
)

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="UTC")


async def refresh_tle() -> None:
    logger.info("TLE refresh started")
    async with AsyncSessionLocal() as db:
        try:
            count = await fetch_and_store_tle(db, url=CELESTRAK_URL)
            if count == 0:
                # Only fall back to stations when DB is empty (cold start).
                # If DB already has data, the active group simply hasn't updated yet.
                existing = await get_latest_tle_snapshots(db)
                if not existing:
                    count = await fetch_and_store_tle(db, url=CELESTRAK_STATIONS_URL)
        except httpx.HTTPError:
            logger.error("TLE refresh failed: CelesTrak unavailable")
            return

    if count > 0:
        await cache_clear_pattern("satlas:overhead:*")
        await cache_clear_pattern("satlas:positions")

    logger.info("TLE refresh complete, processed %d satellites", count)


def start_scheduler() -> None:
    _scheduler.add_job(
        refresh_tle, CronTrigger(hour=0, minute=0), id="tle_refresh_0000"
    )
    _scheduler.add_job(
        refresh_tle, CronTrigger(hour=12, minute=0), id="tle_refresh_1200"
    )
    _scheduler.start()


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
