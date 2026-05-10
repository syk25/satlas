"""Celery app for out-of-process background work (ADR-021).

The web API process owns request handling and the lightweight in-process
schedules (TLE refresh, positions warm). Anything CPU- or memory-heavy that
would otherwise contend with request handlers runs here as Celery tasks on
a separate Fly machine.

ADR-001 fixed Celery + Redis as the queue stack; this is where it lands.
"""

import logging
from datetime import timedelta

from celery import Celery
from celery.signals import beat_init, worker_process_init

from app.config import settings

logger = logging.getLogger(__name__)


celery_app = Celery(
    "satlas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # one country sweep at a time per worker
    task_time_limit=15 * 60,  # hard kill at 15 min — a sweep should never run longer
    task_soft_time_limit=10 * 60,
)

celery_app.conf.beat_schedule = {
    "prewarm-overhead-every-15-min": {
        "task": "app.tasks.prewarm_overhead_all_countries",
        "schedule": timedelta(minutes=15),
    },
}


@beat_init.connect
def _kickstart_prewarm(**_kwargs) -> None:
    """Fire the prewarm fan-out once when beat boots so a fresh deploy
    doesn't leave the cache cold for up to one full schedule interval.
    Runs only in the beat process; beat is single-instance by design."""
    from app.tasks import prewarm_overhead_all_countries

    prewarm_overhead_all_countries.delay()
    logger.info("beat_init: kickstarted prewarm fanout")


@worker_process_init.connect
def _init_worker_process(**_kwargs) -> None:
    """Boot-time setup for each Celery worker process.

    Loads country polygons (used by simulate_overhead_window) and initializes
    Sentry. Called once per forked worker process, not per task.
    """
    from app.services.boundaries import load_country_polygons

    load_country_polygons()

    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[CeleryIntegration()],
            traces_sample_rate=0.2,
            environment=settings.environment,
            send_default_pii=False,
        )
        logger.info("celery worker: sentry initialized")
