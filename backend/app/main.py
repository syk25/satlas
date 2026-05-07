from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import satellites
from app.services.boundaries import load_country_polygons
from app.services.cache import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_country_polygons()
    await init_redis()
    yield
    await close_redis()


app = FastAPI(title="Satlas API", version="0.1.0", lifespan=lifespan)

app.include_router(satellites.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
