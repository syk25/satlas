from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import boundaries
from app.services.position import get_position
from app.services.tle_ingest import (
    CELESTRAK_STATIONS_URL,
    CELESTRAK_URL,
    fetch_and_store_tle,
    get_latest_tle_snapshots,
)

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/satellites", tags=["satellites"])


class SatelliteOverhead(BaseModel):
    norad_id: int
    name: str
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
) -> list[SatelliteOverhead]:
    cc = country_code.upper()

    if not boundaries.country_exists(cc):
        raise HTTPException(status_code=404, detail=f"Country '{cc}' not found.")

    rows = await get_latest_tle_snapshots(db)

    # Seed DB on first request if empty.
    # Falls back to stations group if active group is rate-limited.
    if not rows:
        try:
            count = await fetch_and_store_tle(db, url=CELESTRAK_URL)
            if count == 0:
                await fetch_and_store_tle(db, url=CELESTRAK_STATIONS_URL)
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=503,
                detail="TLE data source unavailable. Try again later.",
            ) from e
        rows = await get_latest_tle_snapshots(db)

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

    return result
