import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import AsyncSessionLocal
from app.services.cache import cache_clear_pattern
from app.services.tle_ingest import refresh_tle, warm_positions_cache

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
        await cache_clear_pattern("satlas:overhead:*")
        await cache_clear_pattern("satlas:positions")
        await cache_clear_pattern("satlas:positions:all")
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
    if seed_immediately:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        _scheduler.add_job(refresh_tle_job, DateTrigger(run_date=run_at), id="tle_seed")
    # warm positions immediately on startup (10s delay so DB connection settles)
    boot_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    _scheduler.add_job(
        warm_positions_job, DateTrigger(run_date=boot_at), id="warm_positions_boot"
    )
    _scheduler.start()


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
