import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.satellite import SatelliteCategory
from app.services import boundaries, cache
from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY

router = APIRouter(prefix="/satellites", tags=["satellites"])

OVERHEAD_CACHE_TTL = 60  # seconds
POSITIONS_CACHE_TTL = 60  # seconds
POSITIONS_CACHE_KEY = "satlas:positions"


class SatellitePosition(BaseModel):
    norad_id: int
    name: str
    lat: float
    lon: float


class SatelliteOverhead(BaseModel):
    norad_id: int
    name: str
    category: str | None
    operator_country: str | None
    operator_name: str | None
    operator_type: str | None
    orbit_class: str | None
    launch_date: str | None
    line1: str
    line2: str
    entry_time: datetime


@router.get("/overhead/{country_code}", response_model=list[SatelliteOverhead])
async def get_overhead(
    country_code: str,
    category: str | None = None,
) -> list[SatelliteOverhead]:
    cc = country_code.upper()

    if not boundaries.country_exists(cc):
        raise HTTPException(status_code=404, detail=f"Country '{cc}' not found.")

    cat_filter_value: str | None = None
    if category:
        try:
            cat_filter_value = SatelliteCategory(category.upper()).value
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Unknown category '{category}'."
            ) from e

    cache_key = f"satlas:overhead:{cc}" + (f":{category}" if category else "")
    cached = await cache.cache_get(cache_key)
    if cached is not None:
        return [SatelliteOverhead(**item) for item in json.loads(cached)]

    all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
    if all_json is None:
        raise HTTPException(
            status_code=503,
            detail="Satellite data is not yet available. Try again shortly.",
        )

    all_positions: list[dict] = json.loads(all_json)
    if cat_filter_value:
        all_positions = [
            p for p in all_positions if p.get("category") == cat_filter_value
        ]

    now = datetime.now(timezone.utc)

    def _filter() -> list[SatelliteOverhead]:
        result = []
        for p in all_positions:
            if boundaries.is_over_country(p["lat"], p["lon"], cc):
                result.append(
                    SatelliteOverhead(
                        norad_id=p["norad_id"],
                        name=p["name"],
                        category=p["category"],
                        operator_country=p.get("operator_country"),
                        operator_name=None,
                        operator_type=None,
                        orbit_class=p["orbit_class"],
                        launch_date=p.get("launch_date"),
                        line1=p["line1"],
                        line2=p["line2"],
                        entry_time=now,
                    )
                )
        return result

    result = await asyncio.to_thread(_filter)

    await cache.cache_set(
        cache_key,
        json.dumps([item.model_dump(mode="json") for item in result]),
        ttl=OVERHEAD_CACHE_TTL,
    )

    return result


@router.get("/positions", response_model=list[SatellitePosition])
async def get_positions() -> list[SatellitePosition]:
    cached = await cache.cache_get(POSITIONS_CACHE_KEY)
    if cached is not None:
        return [SatellitePosition(**item) for item in json.loads(cached)]

    all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
    if all_json is None:
        raise HTTPException(
            status_code=503,
            detail="Satellite data is not yet available. Try again shortly.",
        )

    all_positions: list[dict] = json.loads(all_json)
    result = [
        SatellitePosition(
            norad_id=p["norad_id"],
            name=p["name"],
            lat=round(p["lat"], 4),
            lon=round(p["lon"], 4),
        )
        for p in all_positions
    ]

    await cache.cache_set(
        POSITIONS_CACHE_KEY,
        json.dumps([item.model_dump() for item in result]),
        ttl=POSITIONS_CACHE_TTL,
    )

    return result
