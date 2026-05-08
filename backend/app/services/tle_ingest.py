import asyncio
import csv
import io
import json
import logging
import math
from datetime import date, datetime, timezone
from typing import NamedTuple

from sgp4 import omm as sgp4_omm
from sgp4.api import Satrec
from sgp4.exporter import export_tle
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satellite import (
    ObjectType,
    OrbitClass,
    RcsSize,
    Satellite,
    SatelliteCategory,
    TleSnapshot,
)
from app.services.position import get_position

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"


class TleEntry(NamedTuple):
    """One satellite parsed from a CelesTrak JSON feed."""

    name: str
    line1: str
    line2: str
    country_code: str | None
    launch_date: date | None
    decay_date: date | None
    international_designator: str | None
    object_type: ObjectType | None
    rcs_size: RcsSize | None


# CelesTrak SATCAT abbreviates these in the OBJECT_TYPE column.
_OBJECT_TYPE_MAP = {
    "PAY": ObjectType.PAYLOAD,
    "R/B": ObjectType.ROCKET_BODY,
    "DEB": ObjectType.DEBRIS,
    "TBA": ObjectType.UNKNOWN,
    "UNK": ObjectType.UNKNOWN,
}


def _bucket_rcs(value: str | None) -> RcsSize | None:
    """Convert numeric RCS (m²) from SATCAT to LARGE/MEDIUM/SMALL.

    CelesTrak's bucketing convention: <0.1 = SMALL, 0.1–1.0 = MEDIUM, >1.0 = LARGE.
    Empty / non-numeric values return None.
    """
    if not value or not value.strip():
        return None
    try:
        rcs = float(value)
    except ValueError:
        return None
    if rcs < 0.1:
        return RcsSize.SMALL
    if rcs <= 1.0:
        return RcsSize.MEDIUM
    return RcsSize.LARGE


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


def _parse_launch_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# SATCAT enrichment cache (NORAD ID → metadata dict). Populated via
# /admin/satcat/ingest and consumed during _upsert_entries. Module-level
# memory is sufficient — on app restart, the next GHA run repopulates it,
# and DB rows already have the previous values.
_SATCAT_CACHE: dict[int, dict] = {}


def parse_satcat_csv(raw: str) -> dict[int, dict]:
    """Parse CelesTrak SATCAT CSV into a NORAD ID → metadata dict.

    Columns we read (from satcat.csv header):
    OBJECT_NAME, OBJECT_ID, NORAD_CAT_ID, OBJECT_TYPE, OPS_STATUS_CODE,
    OWNER, LAUNCH_DATE, LAUNCH_SITE, DECAY_DATE, ..., RCS, ...
    """
    reader = csv.DictReader(io.StringIO(raw))
    result: dict[int, dict] = {}
    for row in reader:
        try:
            norad_id = int(row.get("NORAD_CAT_ID") or 0)
        except (TypeError, ValueError):
            continue
        if not norad_id:
            continue
        result[norad_id] = {
            "country_code": (row.get("OWNER") or "").strip() or None,
            "launch_date": _parse_launch_date(row.get("LAUNCH_DATE")),
            "decay_date": _parse_launch_date(row.get("DECAY_DATE")),
            "international_designator": (row.get("OBJECT_ID") or "").strip() or None,
            "object_type": _OBJECT_TYPE_MAP.get(
                (row.get("OBJECT_TYPE") or "").strip().upper()
            ),
            "rcs_size": _bucket_rcs(row.get("RCS")),
        }
    return result


def set_satcat_cache(satcat: dict[int, dict]) -> None:
    """Replace the SATCAT enrichment cache wholesale."""
    global _SATCAT_CACHE
    _SATCAT_CACHE = satcat
    logger.info("SATCAT cache updated: %d entries", len(satcat))


def get_satcat_size() -> int:
    return len(_SATCAT_CACHE)


def _parse_omm_entries(raw: str) -> list[TleEntry]:
    """Parse CelesTrak GP JSON (OMM mean-elements) into TleEntry tuples.

    GP JSON does not include TLE lines, only mean elements. We synthesize
    line1/line2 via sgp4's exporter so downstream code (DB, frontend
    satellite.js) keeps working with TLE strings unchanged.

    GP JSON also does not include COUNTRY_CODE / LAUNCH_DATE / OBJECT_TYPE /
    RCS_SIZE — those fields are populated from the SATCAT cache by
    _upsert_entries, keyed on NORAD ID.
    """
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    entries: list[TleEntry] = []
    for item in items:
        name = item.get("OBJECT_NAME")
        if not name or item.get("NORAD_CAT_ID") is None:
            continue
        try:
            sat = Satrec()
            sgp4_omm.initialize(sat, item)
            line1, line2 = export_tle(sat)
        except (ValueError, KeyError, TypeError) as exc:
            logger.debug(
                "OMM→TLE export failed for %s (%s): %s",
                name,
                item.get("NORAD_CAT_ID"),
                exc,
            )
            continue
        entries.append(
            TleEntry(
                name=name.strip(),
                line1=line1,
                line2=line2,
                # Metadata from SATCAT, applied during upsert.
                country_code=None,
                launch_date=None,
                decay_date=None,
                international_designator=(item.get("OBJECT_ID") or None),
                object_type=None,
                rcs_size=None,
            )
        )
    return entries


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


async def _fetch_raw(group: str) -> list[TleEntry]:
    url = BASE_URL.format(group=group)
    for attempt in range(3):
        try:
            status, body = await asyncio.to_thread(_fetch_raw_sync, url)
            if "GP data has not updated" in body:
                return []
            if status not in (200, 403):
                logger.warning("%s: unexpected status %d", group, status)
                return []
            entries = _parse_omm_entries(body)
            if not entries:
                logger.warning(
                    "%s: status=%d but no entries parsed. body[:200]=%r",
                    group,
                    status,
                    body[:200],
                )
            return entries
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


async def _upsert_entries(
    db: AsyncSession,
    entries: list[TleEntry],
    category: SatelliteCategory,
    now: datetime,
) -> int:
    """Bulk-upsert one feed's entries into the DB. Returns satellite count."""
    sat_rows = []
    tle_meta: list[tuple[int, str, str, datetime]] = []
    for entry in entries:
        norad_id = int(entry.line2[2:7])
        # SATCAT carries the human metadata; OMM only gives us OBJECT_ID.
        # Fall back to OMM's OBJECT_ID for the international designator if
        # SATCAT doesn't have an entry (rare, but possible for newly-launched
        # objects that show up in gp.php before the next satcat refresh).
        sc = _SATCAT_CACHE.get(norad_id, {})
        sat_rows.append(
            {
                "norad_id": norad_id,
                "name": entry.name,
                "is_active": True,
                "category": category,
                "orbit_class": orbit_class_from_tle(entry.line2),
                "operator_country": sc.get("country_code"),
                "launch_date": sc.get("launch_date"),
                "decay_date": sc.get("decay_date"),
                "international_designator": (
                    sc.get("international_designator") or entry.international_designator
                ),
                "object_type": sc.get("object_type"),
                "rcs_size": sc.get("rcs_size"),
            }
        )
        tle_meta.append((norad_id, entry.line1, entry.line2, _parse_epoch(entry.line1)))

    norad_to_id: dict[int, int] = {}
    for i in range(0, len(sat_rows), _BATCH):
        chunk = sat_rows[i : i + _BATCH]
        ins = pg_insert(Satellite).values(chunk)
        # CelesTrak is canonical for these metadata fields — always overwrite.
        # Category is held back on the OTHER (catch-all) feed so a more specific
        # earlier feed doesn't lose its label.
        update_set = {
            "name": ins.excluded.name,
            "orbit_class": ins.excluded.orbit_class,
            "operator_country": ins.excluded.operator_country,
            "launch_date": ins.excluded.launch_date,
            "decay_date": ins.excluded.decay_date,
            "international_designator": ins.excluded.international_designator,
            "object_type": ins.excluded.object_type,
            "rcs_size": ins.excluded.rcs_size,
        }
        if category != SatelliteCategory.OTHER:
            update_set["category"] = ins.excluded.category
        stmt = ins.on_conflict_do_update(
            index_elements=["norad_id"],
            set_=update_set,
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


async def ingest_feed(db: AsyncSession, group: str, raw_json: str) -> int:
    """Parse CelesTrak GP JSON (OMM) pushed from GitHub Actions and upsert.

    Called by the admin endpoint; decouples CelesTrak fetching from the server
    so GitHub Actions runners (non-datacenter IPs) can pull the data instead.
    SATCAT enrichment uses the in-memory cache populated by /admin/satcat/ingest.
    Returns number of satellites processed.
    """
    category = _GROUP_TO_CATEGORY.get(group)
    if category is None:
        raise ValueError(f"Unknown TLE group: {group!r}")
    entries = _parse_omm_entries(raw_json)
    if not entries:
        logger.warning("ingest_feed: no entries in payload for group=%s", group)
        return 0
    logger.info(
        "ingest_feed: %s: %d entries received (satcat cache: %d)",
        group,
        len(entries),
        len(_SATCAT_CACHE),
    )
    now = datetime.now(timezone.utc)
    count = await _upsert_entries(db, entries, category, now)
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
        entries = await _fetch_raw(group)
        if not entries:
            logger.warning("[%d/%d] feed empty or failed: %s", idx, feed_count, group)
            continue
        logger.info(
            "[%d/%d] %s: %d entries received", idx, feed_count, group, len(entries)
        )

        count = await _upsert_entries(db, entries, category, now)
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


async def _fetch_position_rows(db: AsyncSession) -> list[tuple]:
    """Fetch only the 6 columns needed for position computation.

    Column-level SELECT avoids hydrating full ORM objects — reduces memory
    by ~5x compared to get_latest_tle_snapshots() on 16,000+ rows.
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
        select(
            Satellite.norad_id,
            Satellite.name,
            Satellite.category,
            Satellite.orbit_class,
            Satellite.operator_country,
            Satellite.launch_date,
            Satellite.decay_date,
            Satellite.international_designator,
            Satellite.object_type,
            Satellite.rcs_size,
            TleSnapshot.line1,
            TleSnapshot.line2,
        )
        .join(TleSnapshot, Satellite.id == TleSnapshot.satellite_id)
        .join(
            subq,
            (TleSnapshot.satellite_id == subq.c.satellite_id)
            & (TleSnapshot.ingested_at == subq.c.max_ingested),
        )
        .where(Satellite.is_active == True)  # noqa: E712
        .distinct(Satellite.norad_id)
    )
    result = await db.execute(q)
    return result.all()


async def warm_positions_cache(db: AsyncSession) -> int:
    """Pre-compute all satellite positions and store in Redis.

    Called every 60 s by the scheduler. The overhead endpoint reads from
    this cache and runs polygon filtering only, eliminating per-request
    SGP4 computation in the async event loop.
    """
    from app.services.cache import cache_set

    rows = await _fetch_position_rows(db)
    if not rows:
        return 0

    now = datetime.now(timezone.utc)

    def _compute() -> list[dict]:
        result = []
        for (
            norad_id,
            name,
            category,
            orbit_class,
            operator_country,
            launch_date,
            decay_date,
            international_designator,
            object_type,
            rcs_size,
            line1,
            line2,
        ) in rows:
            pos = get_position(line1.strip(), line2.strip(), at=now)
            if pos is None:
                continue
            lat, lon, _ = pos
            result.append(
                {
                    "norad_id": norad_id,
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "category": category.value if category else None,
                    "orbit_class": orbit_class.value if orbit_class else None,
                    "operator_country": operator_country,
                    "launch_date": launch_date.isoformat() if launch_date else None,
                    "decay_date": decay_date.isoformat() if decay_date else None,
                    "international_designator": international_designator,
                    "object_type": object_type.value if object_type else None,
                    "rcs_size": rcs_size.value if rcs_size else None,
                    "line1": line1.strip(),
                    "line2": line2.strip(),
                }
            )
        return result

    positions = await asyncio.to_thread(_compute)
    await cache_set(
        POSITIONS_ALL_CACHE_KEY, json.dumps(positions), ttl=POSITIONS_ALL_CACHE_TTL
    )
    logger.info("warm_positions_cache: cached %d satellite positions", len(positions))
    return len(positions)
