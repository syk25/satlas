import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.satellite import SatelliteCategory
from app.services import boundaries, cache
from app.services.overhead_simulation import simulate_overhead_window
from app.services.tle_ingest import POSITIONS_ALL_CACHE_KEY
from app.services.visit_frequency import _visits_key

router = APIRouter(prefix="/satellites", tags=["satellites"])

# 20-min cache per (country, category, include_inactive). ADR-020 introduced
# a 15-min scheduler that prewarms the default-case cache for every country;
# TTL must be longer than the prewarm interval so a slow tick cannot leave
# the cache empty between cycles.
OVERHEAD_CACHE_TTL = 1200
POSITIONS_CACHE_TTL = 60
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
    operator: str | None
    operator_name: str | None
    operator_type: str | None
    orbit_class: str | None
    launch_date: str | None
    decay_date: str | None
    international_designator: str | None
    object_type: str | None
    rcs_size: str | None
    line1: str
    line2: str
    entry_time: datetime
    exit_time: datetime
    passes_24h: int | None  # ADR-019; None when precompute hasn't run yet


@router.get("/overhead/{country_code}", response_model=list[SatelliteOverhead])
async def get_overhead(
    country_code: str,
    category: str | None = None,
    include_inactive: bool = False,
) -> list[SatelliteOverhead]:
    """Satellites currently over the given country.

    By default returns only PAYLOAD object types — actual operating satellites.
    Set `include_inactive=true` to also include rocket bodies, debris, and
    unclassified objects (~half of the active catalog).
    """
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

    cache_key = (
        f"satlas:overhead:{cc}"
        + (f":{category}" if category else "")
        + (":all" if include_inactive else "")
    )
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
    if not include_inactive:
        # Default view: only real operating satellites. Treat NULL object_type
        # as PAYLOAD so legacy rows aren't hidden until the next ingest cycle
        # backfills them.
        all_positions = [
            p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
        ]
    if cat_filter_value:
        all_positions = [
            p for p in all_positions if p.get("category") == cat_filter_value
        ]

    now = datetime.now(timezone.utc)

    windowed = await asyncio.to_thread(simulate_overhead_window, cc, all_positions, now)

    # ADR-019: enrich with 24h pass counts. One HMGET per overhead request,
    # not per satellite. If the visit precompute hasn't run yet, all values
    # come back None and the field gracefully degrades to null in the response.
    norad_fields = [str(p["norad_id"]) for p in windowed]
    pass_counts_raw = await cache.cache_hash_mget(_visits_key(cc), norad_fields)
    pass_counts: list[int | None] = [
        int(v) if v is not None else None for v in pass_counts_raw
    ]

    result = [
        SatelliteOverhead(
            norad_id=p["norad_id"],
            name=p["name"],
            category=p["category"],
            operator=p.get("operator"),
            operator_name=None,
            operator_type=None,
            orbit_class=p["orbit_class"],
            launch_date=p.get("launch_date"),
            decay_date=p.get("decay_date"),
            international_designator=p.get("international_designator"),
            object_type=p.get("object_type"),
            rcs_size=p.get("rcs_size"),
            line1=p["line1"],
            line2=p["line2"],
            entry_time=p["entry_time"],
            exit_time=p["exit_time"],
            passes_24h=pass_counts[i],
        )
        for i, p in enumerate(windowed)
    ]

    await cache.cache_set(
        cache_key,
        json.dumps([item.model_dump(mode="json") for item in result]),
        ttl=OVERHEAD_CACHE_TTL,
    )

    return result


@router.get("/positions", response_model=list[SatellitePosition])
async def get_positions(include_inactive: bool = False) -> list[SatellitePosition]:
    """All satellite positions for the global map view.

    Defaults to PAYLOAD only so the map shows operating satellites, not debris.
    """
    # NB: avoid suffix `:all` here — it collides with POSITIONS_ALL_CACHE_KEY,
    # the master cache that this endpoint reads from.
    cache_key = POSITIONS_CACHE_KEY + (":full" if include_inactive else "")
    cached = await cache.cache_get(cache_key)
    if cached is not None:
        return [SatellitePosition(**item) for item in json.loads(cached)]

    all_json = await cache.cache_get(POSITIONS_ALL_CACHE_KEY)
    if all_json is None:
        raise HTTPException(
            status_code=503,
            detail="Satellite data is not yet available. Try again shortly.",
        )

    all_positions: list[dict] = json.loads(all_json)
    if not include_inactive:
        all_positions = [
            p for p in all_positions if p.get("object_type") in (None, "PAYLOAD")
        ]
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
        cache_key,
        json.dumps([item.model_dump() for item in result]),
        ttl=POSITIONS_CACHE_TTL,
    )

    return result
