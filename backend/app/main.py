import logging as _logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.satellite import Satellite
from app.routers import admin, satellites, stats
from app.services.boundaries import load_country_polygons
from app.services.cache import close_redis, init_redis
from app.services.scheduler import start_scheduler, stop_scheduler

_startup_log = _logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,
        environment=settings.environment,
        send_default_pii=False,
    )
    print("[sentry] initialized, environment =", settings.environment, flush=True)
else:
    print("[sentry] SENTRY_DSN not set — disabled", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_country_polygons()
    await init_redis()

    # Seed check is best-effort. The upstream Postgres has been dropping
    # connections mid-query (the same `ConnectionDoesNotExistError` we
    # already chase down in alembic/env.py); when it does, lifespan must
    # not crash the app. /overhead and /passes serve from Redis without
    # touching the DB, so the API is still useful while Postgres is
    # flaky — better to boot degraded than to refuse requests entirely.
    seed = False
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count()).select_from(Satellite))
            seed = (result.scalar() or 0) < 5000
    except Exception:  # noqa: BLE001 — boot-degraded; specific causes vary
        _startup_log.exception(
            "Seed check failed; booting without re-seed. DB-touching jobs"
            " (warm_positions, visits/recompute) will recover when DB is reachable."
        )

    start_scheduler(seed_immediately=seed)
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(title="Satlas API", version="0.1.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(satellites.router)
app.include_router(admin.router)
app.include_router(stats.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
