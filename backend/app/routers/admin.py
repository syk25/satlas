import asyncio
import gc
import logging
import secrets
import time

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services import boundaries
from app.services.tle_ingest import (
    get_satcat_size,
    ingest_feed,
    parse_satcat_csv,
    set_satcat_cache,
    stream_position_rows,
)
from app.services.visit_frequency import (
    begin_recompute,
    compute_24h_passes,
    store_passes_chunk,
)

# Chunk size for the recompute sweep. 1,000 keeps peak memory ≈ a single
# chunk's events (~1MB) while amortising Redis pipeline overhead — smaller
# chunks would trade memory for more round-trips, larger chunks regress
# toward the all-at-once memory cliff that ADR-024 fixes.
RECOMPUTE_CHUNK_SIZE = 1000

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


def _enum_value(x):
    """Unwrap SQLAlchemy Enum instances to their .value string. Plain
    strings and None pass through untouched. The fix for the
    "Object of type SatelliteCategory is not JSON serializable" regression
    that broke visits/recompute end-to-end (see commit 7780019)."""
    return x.value if x is not None and hasattr(x, "value") else x


def _chunk_to_satellites(chunk_rows) -> list[dict]:
    """Filter a row chunk to PAYLOAD-only and unwrap Enum metadata to
    plain strings. Rocket bodies / debris produce pass counts the overhead
    endpoint never returns, so excluding them keeps the timeline compact
    and matches the dashboard view."""
    return [
        {
            "norad_id": r[0],
            "name": r[1],
            "category": _enum_value(r[2]),
            "orbit_class": _enum_value(r[3]),
            "line1": r[10].strip(),
            "line2": r[11].strip(),
        }
        for r in chunk_rows
        if _enum_value(r[8]) in (None, "PAYLOAD")
    ]


@router.post("/visits/recompute")
async def recompute_visits(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Recompute 24-hour pass counts + timeline per country.

    ADR-019 introduced the sweep; ADR-024 made it chunked. Earlier
    versions built the whole result set in memory before writing to
    Redis — for the production catalog (16k+ satellites, ~80k pass
    events, 12-min walk) that produced an 860MB RSS peak that OOM-killed
    uvicorn before the write step could land. The new flow:

    1. Clear `satlas:visits:24h:*` and `satlas:passes:24h:*` up front so
       chunk-level HINCRBY / RPUSH start from a clean slate.
    2. Stream the satellite catalog from PG via a server-side cursor.
    3. For each chunk: filter to PAYLOAD, run compute in a worker thread,
       append events to Redis (one pipeline per chunk), drop references,
       gc.collect().
    4. Close the per-request Sentry transaction at the start of the
       handler — a 12-minute span chain would accumulate enough metadata
       to OOM on its own under sentry-asgi's default sampling.
    """
    _verify_token(request)

    # Sentry's per-request transaction lasts the full handler. For a 12-min
    # admin sweep the accumulating span tree was a meaningful memory
    # contributor (~100MB observed). Finish it up front; uncaught exceptions
    # still reach Sentry via the global exception handler.
    scope = sentry_sdk.get_current_scope()
    if scope.transaction is not None:
        scope.transaction.finish()

    # Clean slate. Iterating the polygon dict gives us every ISO-A2 code
    # for which we might ever store pass data.
    country_codes = list(boundaries._country_polygons.keys())
    await begin_recompute(country_codes)

    t0 = time.time()
    total_satellites = 0
    total_pairs = 0
    total_timelines = 0
    countries_touched: set[str] = set()

    async for chunk_rows in stream_position_rows(db, chunk_size=RECOMPUTE_CHUNK_SIZE):
        chunk_satellites = _chunk_to_satellites(chunk_rows)
        if not chunk_satellites:
            del chunk_rows
            continue

        chunk_passes = await asyncio.to_thread(compute_24h_passes, chunk_satellites)
        pairs, events = await store_passes_chunk(chunk_passes)

        total_satellites += len(chunk_satellites)
        total_pairs += pairs
        total_timelines += events
        countries_touched.update(chunk_passes.keys())

        # Memory hygiene: drop chunk references explicitly and force a
        # collection so the next chunk starts from a clean baseline. SGP4
        # propagation produces a lot of short-lived Python objects that
        # CPython's generational collector takes a while to reclaim on its
        # own — without this, RSS climbs chunk-by-chunk even though each
        # chunk is small.
        del chunk_rows, chunk_satellites, chunk_passes
        gc.collect()

    if total_satellites == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No satellites in DB yet.",
        )

    elapsed = time.time() - t0
    logger.info(
        "visits/recompute: %d satellites, %d countries, %d pairs, %d events in %.1fs",
        total_satellites,
        len(countries_touched),
        total_pairs,
        total_timelines,
        elapsed,
    )
    if elapsed > 600:
        logger.warning("visits/recompute exceeded 10 minutes: %.1fs", elapsed)

    return {
        "satellites": total_satellites,
        "countries": len(countries_touched),
        "pairs": total_pairs,
        "timelines": total_timelines,
        "elapsed_seconds": round(elapsed, 1),
    }
