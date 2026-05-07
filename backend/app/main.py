import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.satellite import Satellite
from app.routers import satellites
from app.services.boundaries import load_country_polygons
from app.services.cache import close_redis, init_redis
from app.services.scheduler import refresh_tle_job, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_country_polygons()
    await init_redis()
    # Background seeding if DB is sparse — does not block startup or health check
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(Satellite))
        if result.scalar() < 5000:
            asyncio.create_task(refresh_tle_job())
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(title="Satlas API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(satellites.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
