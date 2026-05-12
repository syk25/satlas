"""Aggregated stats for the /dashboard page.

A single endpoint serves the four MVP cards (totals + category breakdown,
top countries by 24h pass count, recent launches). All three sections are
bundled into one HTTP round-trip and cached together — at the 5-minute TTL
the data sources change cadence (12h ingest, ~hourly Redis snapshots) so
finer-grained TTLs would only save a few ms per call.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.satellite import Satellite
from app.services import boundaries, cache
from app.services.visit_frequency import _visits_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])

DASHBOARD_CACHE_KEY = "satlas:stats:dashboard"
DASHBOARD_CACHE_TTL = 300  # 5 min — sources update every ~12h, this is plenty
TOP_COUNTRIES_LIMIT = 10
RECENT_LAUNCHES_LIMIT = 20
RECENT_LAUNCH_WINDOW_DAYS = 30  # 7 days is often empty; 30 keeps the card useful


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    """Return totals + category breakdown, top countries by 24h passes,
    and most recent launches. Single endpoint to keep the dashboard to one
    request; bypasses Pydantic since the payload is already a serialized
    JSON cache hit on the hot path."""
    cached = await cache.cache_get(DASHBOARD_CACHE_KEY)
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    payload = {
        "satellites": await _satellite_totals(db),
        "top_countries": await _top_countries(),
        "recent_launches": await _recent_launches(db),
    }
    serialized = json.dumps(payload)
    await cache.cache_set(DASHBOARD_CACHE_KEY, serialized, ttl=DASHBOARD_CACHE_TTL)
    return Response(content=serialized, media_type="application/json")


async def _satellite_totals(db: AsyncSession) -> dict:
    """Active PAYLOAD count + per-category breakdown in one query."""
    stmt = (
        select(Satellite.category, func.count(Satellite.id))
        .where(
            Satellite.is_active == True,  # noqa: E712
            Satellite.object_type.in_([None, "PAYLOAD"]),
        )
        .group_by(Satellite.category)
    )
    result = await db.execute(stmt)
    by_category: dict[str, int] = {}
    for cat, count in result.all():
        key = cat.value if cat is not None else "OTHER"
        by_category[key] = (by_category.get(key, 0) or 0) + count
    total = sum(by_category.values())
    return {"total": total, "by_category": by_category}


async def _top_countries() -> list[dict]:
    """Aggregate `satlas:visits:24h:{cc}` hashes across all countries via
    a single Redis pipeline. With Redis in-region (ADR-023) this is sub-ms
    per key, so the 234-country aggregation costs ~50ms once per 5 minutes.

    Returns the top N by total 24h pass count. Countries with no visits
    cache yet (precompute hasn't reached them) are silently skipped."""
    codes = list(boundaries._country_polygons.keys())
    if not codes:
        return []

    keys = [_visits_key(cc) for cc in codes]
    hashes = await cache.cache_pipeline_hgetall(keys)

    totals: list[dict] = []
    for cc, hash_data in zip(codes, hashes, strict=False):
        if not hash_data:
            continue
        total = 0
        for v in hash_data.values():
            try:
                total += int(v)
            except (TypeError, ValueError):
                continue
        if total > 0:
            totals.append({"cc": cc, "passes_24h": total})

    totals.sort(key=lambda x: x["passes_24h"], reverse=True)
    return totals[:TOP_COUNTRIES_LIMIT]


async def _recent_launches(db: AsyncSession) -> list[dict]:
    """Most recent PAYLOAD launches in the past `RECENT_LAUNCH_WINDOW_DAYS`."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(
        days=RECENT_LAUNCH_WINDOW_DAYS
    )
    stmt = (
        select(
            Satellite.norad_id,
            Satellite.name,
            Satellite.launch_date,
            Satellite.operator,
            Satellite.category,
        )
        .where(
            Satellite.is_active == True,  # noqa: E712
            Satellite.launch_date >= cutoff,
            Satellite.object_type.in_([None, "PAYLOAD"]),
        )
        .order_by(Satellite.launch_date.desc())
        .limit(RECENT_LAUNCHES_LIMIT)
    )
    result = await db.execute(stmt)
    return [
        {
            "norad_id": norad_id,
            "name": name,
            "launch_date": launch_date.isoformat() if launch_date else None,
            "operator": operator,
            "category": category.value if category is not None else None,
        }
        for norad_id, name, launch_date, operator, category in result.all()
    ]
