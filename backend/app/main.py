from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import satellites
from app.services.boundaries import load_country_polygons


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_country_polygons()
    yield


app = FastAPI(title="Satlas API", version="0.1.0", lifespan=lifespan)

app.include_router(satellites.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
