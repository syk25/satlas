import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
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


def start_scheduler(seed_immediately: bool = False) -> None:
    """Register the in-process schedules owned by the API machine.

    ADR-015: TLE ingest is push-model — GitHub Actions fetches CelesTrak
    (Fly IPs are blocked from CelesTrak's larger feeds) and pushes via
    `/admin/tle/ingest/{group}`. The in-process 00:00 / 12:00 UTC TLE
    cron jobs were dead weight in production: every fetch attempt
    timed out against the IP block, but the surrounding work still
    pinned a DB session and a thread-pool slot while the 18-feed
    retry loop ground through. Two consecutive midnight-UTC GHA push
    runs returned 500s on ingest while these jobs were still active,
    so they are gone.

    `refresh_tle_job` is retained as a `seed_immediately` hook for
    local dev where the DB starts empty — the dev machine is not IP
    blocked and the fetch actually succeeds.

    ADR-021: overhead prewarm has moved to a Celery worker process.
    Scheduler now only owns positions cache warming (every 60 s).
    """
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
