import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.tle_ingest import (
    _fetch_position_rows,
    get_satcat_size,
    ingest_feed,
    parse_satcat_csv,
    set_satcat_cache,
)
from app.services.visit_frequency import compute_24h_passes, store_passes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_token(request: Request) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin token not configured",
        )
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


@router.post("/tle/ingest/{group}")
async def push_tle_feed(
    group: str,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Receive CelesTrak GP JSON (OMM mean elements) from GitHub Actions.

    GitHub Actions runners use non-datacenter IPs not blocked by CelesTrak,
    so they fetch the data and push it here. TLE lines are synthesized from
    the OMM elements; SATCAT-sourced metadata (operator country, launch date,
    object type, RCS size) is applied per NORAD ID from the in-memory SATCAT
    cache populated by /admin/satcat/ingest.
    """
    _verify_token(request)
    raw = (await request.body()).decode("utf-8", errors="replace")
    if not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty body"
        )
    try:
        count = await ingest_feed(db, group, raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return {"group": group, "satellites": count}


@router.post("/satcat/ingest")
async def push_satcat(request: Request) -> dict:
    """Receive CelesTrak SATCAT CSV and load it into the in-memory cache.

    Must be pushed BEFORE the TLE feeds in each refresh cycle so ingest_feed
    can enrich satellites with operator country, launch date, object type,
    and RCS size on upsert.
    """
    _verify_token(request)
    raw = (await request.body()).decode("utf-8", errors="replace")
    if not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty body"
        )
    satcat = parse_satcat_csv(raw)
    if not satcat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No rows parsed"
        )
    set_satcat_cache(satcat)
    return {"entries": get_satcat_size()}


@router.post("/visits/recompute")
async def recompute_visits(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Recompute 24-hour pass counts per country (ADR-019).

    Called by GitHub Actions after the final TLE feed push, so the result
    reflects the freshly ingested catalog. The sweep takes ~5 minutes on
    16k+ satellites; runs in a worker thread to keep the event loop free.
    """
    _verify_token(request)

    rows = await _fetch_position_rows(db)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No satellites in DB yet.",
        )

    satellites = [
        {"norad_id": r[0], "line1": r[10].strip(), "line2": r[11].strip()} for r in rows
    ]

    t0 = time.time()
    passes = await asyncio.to_thread(compute_24h_passes, satellites)
    elapsed = time.time() - t0
    pairs, timelines = await store_passes(passes)

    logger.info(
        "visits/recompute: %d satellites, %d countries, %d pairs, "
        "%d timelines in %.1fs",
        len(satellites),
        len(passes),
        pairs,
        timelines,
        elapsed,
    )
    if elapsed > 600:
        logger.warning("visits/recompute exceeded 10 minutes: %.1fs", elapsed)

    return {
        "satellites": len(satellites),
        "countries": len(passes),
        "pairs": pairs,
        "timelines": timelines,
        "elapsed_seconds": round(elapsed, 1),
    }
