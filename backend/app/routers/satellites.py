import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.satellite import SatelliteCategory
from app.services import boundaries, cache
from app.services.position import get_position
from app.services.tle_ingest import get_latest_tle_snapshots

DbSession = Annotated[AsyncSession, Depends(get_db)]

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
    line1: str
    line2: str
    entry_time: datetime


@router.get("/overhead/{country_code}", response_model=list[SatelliteOverhead])
async def get_overhead(
    country_code: str,
    db: DbSession,
    category: str | None = None,
) -> list[SatelliteOverhead]:
    cc = country_code.upper()

    if not boundaries.country_exists(cc):
        raise HTTPException(status_code=404, detail=f"Country '{cc}' not found.")

    cat_filter: SatelliteCategory | None = None
    if category:
        try:
            cat_filter = SatelliteCategory(category.upper())
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Unknown category '{category}'."
            ) from e

    cache_key = f"satlas:overhead:{cc}" + (f":{category}" if category else "")
    cached = await cache.cache_get(cache_key)
    if cached is not None:
        return [SatelliteOverhead(**item) for item in json.loads(cached)]

    rows = await get_latest_tle_snapshots(db, category=cat_filter)
    if not rows:
        raise HTTPException(
            status_code=503,
            detail="Satellite data is not yet available. Try again shortly.",
        )

    now = datetime.now(timezone.utc)
    result = []

    for satellite, snapshot in rows:
        pos = get_position(snapshot.line1.strip(), snapshot.line2.strip(), at=now)
        if pos is None:
            continue
        lat, lon, _ = pos
        if boundaries.is_over_country(lat, lon, cc):
            result.append(
                SatelliteOverhead(
                    norad_id=satellite.norad_id,
                    name=satellite.name,
                    category=satellite.category.value if satellite.category else None,
                    operator_country=satellite.operator_country,
                    operator_name=satellite.operator_name,
                    operator_type=(
                        satellite.operator_type.value
                        if satellite.operator_type
                        else None
                    ),
                    orbit_class=(
                        satellite.orbit_class.value if satellite.orbit_class else None
                    ),
                    line1=snapshot.line1.strip(),
                    line2=snapshot.line2.strip(),
                    entry_time=now,
                )
            )

    await cache.cache_set(
        cache_key,
        json.dumps([item.model_dump(mode="json") for item in result]),
        ttl=OVERHEAD_CACHE_TTL,
    )

    return result


@router.get("/positions", response_model=list[SatellitePosition])
async def get_positions(db: DbSession) -> list[SatellitePosition]:
    cached = await cache.cache_get(POSITIONS_CACHE_KEY)
    if cached is not None:
        return [SatellitePosition(**item) for item in json.loads(cached)]

    rows = await get_latest_tle_snapshots(db)
    if not rows:
        raise HTTPException(
            status_code=503,
            detail="Satellite data is not yet available. Try again shortly.",
        )

    now = datetime.now(timezone.utc)
    result: list[SatellitePosition] = []

    for satellite, snapshot in rows:
        pos = get_position(snapshot.line1.strip(), snapshot.line2.strip(), at=now)
        if pos is None:
            continue
        lat, lon, _ = pos
        result.append(
            SatellitePosition(
                norad_id=satellite.norad_id,
                name=satellite.name,
                lat=round(lat, 4),
                lon=round(lon, 4),
            )
        )

    await cache.cache_set(
        POSITIONS_CACHE_KEY,
        json.dumps([item.model_dump() for item in result]),
        ttl=POSITIONS_CACHE_TTL,
    )

    return result
