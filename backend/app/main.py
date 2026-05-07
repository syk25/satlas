from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import satellites
from app.services.boundaries import load_country_polygons
from app.services.cache import close_redis, init_redis
from app.services.scheduler import refresh_tle, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_country_polygons()
    await init_redis()
    await refresh_tle()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(title="Satlas API", version="0.1.0", lifespan=lifespan)

app.include_router(satellites.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
