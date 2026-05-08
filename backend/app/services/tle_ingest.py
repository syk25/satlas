import asyncio
import json
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satellite import OrbitClass, Satellite, SatelliteCategory, TleSnapshot
from app.services.position import get_position

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle"

POSITIONS_ALL_CACHE_KEY = "satlas:positions:all"
POSITIONS_ALL_CACHE_TTL = 120  # 60s interval job → always fresh before expiry

# Ordered by priority: specific categories first, OTHER (active) last.
# If a satellite appears in multiple feeds, the first match wins.
CATEGORY_FEEDS: list[tuple[str, SatelliteCategory]] = [
    ("stations", SatelliteCategory.STATION),
    ("weather", SatelliteCategory.WEATHER),
    # "noaa" removed — group no longer exists on CelesTrak; covered by "weather"
    ("goes", SatelliteCategory.WEATHER),
    ("military", SatelliteCategory.MILITARY),
    ("amateur", SatelliteCategory.AMATEUR),
    ("gps-ops", SatelliteCategory.GNSS),
    ("glo-ops", SatelliteCategory.GNSS),
    ("galileo", SatelliteCategory.GNSS),
    ("beidou", SatelliteCategory.GNSS),
    # "starlink" skipped — 403 from datacenter IPs; captured as OTHER via "active"
    ("oneweb", SatelliteCategory.COMMERCIAL),
    # "iridium" removed — old constellation deorbited, group no longer exists
    ("iridium-NEXT", SatelliteCategory.COMMERCIAL),
    ("resource", SatelliteCategory.EARTH_OBS),
    ("planet", SatelliteCategory.EARTH_OBS),
    ("science", SatelliteCategory.SCIENTIFIC),
    ("active", SatelliteCategory.OTHER),  # catch-all incl. Starlink as OTHER
]

_HEADERS = {"User-Agent": "satlas/0.1 (https://github.com/syk25/satlas)"}


def _parse_tle_blocks(raw: str) -> list[tuple[str, str, str]]:
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    blocks = []
    for i in range(0, len(lines) - 2, 3):
        name = lines[i].strip()
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            blocks.append((name, line1, line2))
    return blocks


def _parse_epoch(line1: str) -> datetime:
    epoch_str = line1[18:32].strip()
    year_2d = int(epoch_str[:2])
    year = 2000 + year_2d if year_2d < 57 else 1900 + year_2d
    day_of_year = float(epoch_str[2:])
    day = int(day_of_year)
    frac = day_of_year - day
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    from datetime import timedelta

    return base + timedelta(days=day - 1) + timedelta(days=frac)


def orbit_class_from_tle(line2: str) -> OrbitClass:
    """Derive orbit class from TLE line 2 using mean motion and eccentricity."""
    try:
        mean_motion = float(line2[52:63].strip())  # rev/day
        eccentricity = float("0." + line2[26:33].strip())

        if eccentricity > 0.1:
            return OrbitClass.HEO

        # Semi-major axis from mean motion: a = (μ / n²)^(1/3)
        # μ = 398600.4418 km³/s², n in rad/s
        n_rad_s = mean_motion * 2 * math.pi / 86400.0
        a_km = (398600.4418 / n_rad_s**2) ** (1.0 / 3.0)
        alt_km = a_km - 6371.0

        if alt_km < 2000:
            return OrbitClass.LEO
        elif alt_km < 35500:
            return OrbitClass.MEO
        else:
            return OrbitClass.GEO
    except (ValueError, ZeroDivisionError, IndexError):
        return OrbitClass.LEO


logger = logging.getLogger(__name__)

_BATCH = 500  # rows per bulk statement — stays under pg's 65535-param limit


def _fetch_raw_sync(url: str) -> tuple[int, str]:
    """Synchronous fetch; runs in a thread via asyncio.to_thread."""
    import urllib.request

    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


async def _fetch_raw(group: str) -> list[tuple[str, str, str]]:
    url = BASE_URL.format(group=group)
    for attempt in range(3):
        try:
            status, body = await asyncio.to_thread(_fetch_raw_sync, url)
            if "GP data has not updated" in body:
                return []
            if status not in (200, 403):
                logger.warning("%s: unexpected status %d", group, status)
                return []
            blocks = _parse_tle_blocks(body)
            if not blocks:
                logger.warning(
                    "%s: status=%d but no TLE parsed. body[:200]=%r",
                    group,
                    status,
                    body[:200],
                )
            return blocks
        except OSError as exc:
            logger.warning(
                "%s: request error (attempt %d): %s: %s",
                group,
                attempt,
                type(exc).__name__,
                exc,
            )
            if attempt < 2:
                await asyncio.sleep(5)
    return []


async def _upsert_blocks(
    db: AsyncSession,
    blocks: list[tuple[str, str, str]],
    category: SatelliteCategory,
    now: datetime,
) -> int:
    """Bulk-upsert one feed's TLE blocks into the DB. Returns satellite count."""
    sat_rows = []
    tle_meta: list[tuple[int, str, str, datetime]] = []
    for name, line1, line2 in blocks:
        norad_id = int(line2[2:7])
        sat_rows.append(
            {
                "norad_id": norad_id,
                "name": name,
                "is_active": True,
                "category": category,
                "orbit_class": orbit_class_from_tle(line2),
            }
        )
        tle_meta.append((norad_id, line1, line2, _parse_epoch(line1)))

    norad_to_id: dict[int, int] = {}
    for i in range(0, len(sat_rows), _BATCH):
        chunk = sat_rows[i : i + _BATCH]
        ins = pg_insert(Satellite).values(chunk)
        if category == SatelliteCategory.OTHER:
            stmt = ins.on_conflict_do_update(
                index_elements=["norad_id"],
                set_={
                    "name": ins.excluded.name,
                    "orbit_class": ins.excluded.orbit_class,
                },
            )
        else:
            stmt = ins.on_conflict_do_update(
                index_elements=["norad_id"],
                set_={
                    "name": ins.excluded.name,
                    "category": ins.excluded.category,
                    "orbit_class": ins.excluded.orbit_class,
                },
            )
        result = await db.execute(stmt.returning(Satellite.norad_id, Satellite.id))
        for row in result:
            norad_to_id[row.norad_id] = row.id

    snap_rows = [
        {
            "satellite_id": norad_to_id[norad_id],
            "line1": line1,
            "line2": line2,
            "epoch": epoch,
            "ingested_at": now,
        }
        for norad_id, line1, line2, epoch in tle_meta
        if norad_id in norad_to_id
    ]
    for i in range(0, len(snap_rows), _BATCH):
        await db.execute(pg_insert(TleSnapshot).values(snap_rows[i : i + _BATCH]))

    await db.commit()
    return len(sat_rows)


_GROUP_TO_CATEGORY: dict[str, SatelliteCategory] = dict(CATEGORY_FEEDS)


async def ingest_feed(db: AsyncSession, group: str, raw_tle: str) -> int:
    """Parse raw TLE text pushed from GitHub Actions and upsert to DB.

    Called by the admin endpoint; decouples CelesTrak fetching from the server
    so GitHub Actions runners (non-datacenter IPs) can pull the data instead.
    Returns number of satellites processed.
    """
    category = _GROUP_TO_CATEGORY.get(group)
    if category is None:
        raise ValueError(f"Unknown TLE group: {group!r}")
    blocks = _parse_tle_blocks(raw_tle)
    if not blocks:
        logger.warning("ingest_feed: no TLE blocks in payload for group=%s", group)
        return 0
    logger.info("ingest_feed: %s: %d blocks received", group, len(blocks))
    now = datetime.now(timezone.utc)
    count = await _upsert_blocks(db, blocks, category, now)
    logger.info("ingest_feed: %s: committed %d satellites", group, count)
    return count


async def refresh_tle(db: AsyncSession) -> int:
    """Fetch all category feeds and upsert satellites with category + orbit_class.

    Priority: specific category feeds are processed first. The `active` (OTHER)
    feed runs last so it never overwrites a more specific category already set.
    Returns total number of satellites stored.
    """
    now = datetime.now(timezone.utc)
    total = 0
    feed_count = len(CATEGORY_FEEDS)

    for idx, (group, category) in enumerate(CATEGORY_FEEDS, 1):
        logger.info("[%d/%d] fetching feed: %s", idx, feed_count, group)
        blocks = await _fetch_raw(group)
        if not blocks:
            logger.warning("[%d/%d] feed empty or failed: %s", idx, feed_count, group)
            continue
        logger.info(
            "[%d/%d] %s: %d TLE blocks received", idx, feed_count, group, len(blocks)
        )

        count = await _upsert_blocks(db, blocks, category, now)
        total += count
        logger.info(
            "[%d/%d] %s: committed %d satellites, running total=%d",
            idx,
            feed_count,
            group,
            count,
            total,
        )

        await asyncio.sleep(5)

    return total


async def get_latest_tle_snapshots(
    db: AsyncSession,
    category: SatelliteCategory | None = None,
) -> list[tuple[Satellite, TleSnapshot]]:
    """Return the most recent TLE snapshot for each active satellite.

    Optionally filtered by category.
    """
    from sqlalchemy import func

    subq = (
        select(
            TleSnapshot.satellite_id,
            func.max(TleSnapshot.ingested_at).label("max_ingested"),
        )
        .group_by(TleSnapshot.satellite_id)
        .subquery()
    )

    q = (
        select(Satellite, TleSnapshot)
        .join(TleSnapshot, Satellite.id == TleSnapshot.satellite_id)
        .join(
            subq,
            (TleSnapshot.satellite_id == subq.c.satellite_id)
            & (TleSnapshot.ingested_at == subq.c.max_ingested),
        )
        .where(Satellite.is_active == True)  # noqa: E712
        .distinct(Satellite.id)
    )

    if category is not None:
        q = q.where(Satellite.category == category)

    result = await db.execute(q)
    return result.all()


# Legacy shim used by scheduler — kept for backward compat during transition
async def fetch_and_store_tle(db: AsyncSession, url: str = "") -> int:
    return await refresh_tle(db)


async def warm_positions_cache(db: AsyncSession) -> int:
    """Pre-compute all satellite positions and store in Redis.

    Called every 60 s by the scheduler. The overhead endpoint reads from
    this cache and runs polygon filtering only, eliminating per-request
    SGP4 computation in the async event loop.
    """
    from app.services.cache import cache_set

    rows = await get_latest_tle_snapshots(db)
    if not rows:
        return 0

    now = datetime.now(timezone.utc)

    def _compute() -> list[dict]:
        result = []
        for satellite, snapshot in rows:
            pos = get_position(snapshot.line1.strip(), snapshot.line2.strip(), at=now)
            if pos is None:
                continue
            lat, lon, _ = pos
            result.append(
                {
                    "norad_id": satellite.norad_id,
                    "name": satellite.name,
                    "lat": lat,
                    "lon": lon,
                    "category": satellite.category.value
                    if satellite.category
                    else None,
                    "orbit_class": (
                        satellite.orbit_class.value if satellite.orbit_class else None
                    ),
                    "line1": snapshot.line1.strip(),
                    "line2": snapshot.line2.strip(),
                }
            )
        return result

    positions = await asyncio.to_thread(_compute)
    await cache_set(
        POSITIONS_ALL_CACHE_KEY, json.dumps(positions), ttl=POSITIONS_ALL_CACHE_TTL
    )
    logger.info("warm_positions_cache: cached %d satellite positions", len(positions))
    return len(positions)
