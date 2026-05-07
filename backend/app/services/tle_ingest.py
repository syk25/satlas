import asyncio
import math
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satellite import OrbitClass, Satellite, SatelliteCategory, TleSnapshot

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle"

# Ordered by priority: specific categories first, OTHER (active) last.
# If a satellite appears in multiple feeds, the first match wins.
CATEGORY_FEEDS: list[tuple[str, SatelliteCategory]] = [
    ("stations", SatelliteCategory.STATION),
    ("weather", SatelliteCategory.WEATHER),
    ("noaa", SatelliteCategory.WEATHER),
    ("goes", SatelliteCategory.WEATHER),
    ("military", SatelliteCategory.MILITARY),
    ("amateur", SatelliteCategory.AMATEUR),
    ("gps-ops", SatelliteCategory.GNSS),
    ("glo-ops", SatelliteCategory.GNSS),
    ("galileo", SatelliteCategory.GNSS),
    ("beidou", SatelliteCategory.GNSS),
    ("starlink", SatelliteCategory.COMMERCIAL),
    ("oneweb", SatelliteCategory.COMMERCIAL),
    ("iridium", SatelliteCategory.COMMERCIAL),
    ("iridium-NEXT", SatelliteCategory.COMMERCIAL),
    ("resource", SatelliteCategory.EARTH_OBS),
    ("planet", SatelliteCategory.EARTH_OBS),
    ("science", SatelliteCategory.SCIENTIFIC),
    ("active", SatelliteCategory.OTHER),  # catch-all, lowest priority
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


async def _fetch_raw(
    client: httpx.AsyncClient, group: str
) -> list[tuple[str, str, str]]:
    url = BASE_URL.format(group=group)
    try:
        resp = await client.get(url)
        body = resp.text
        if "GP data has not updated" in body:
            return []
        if resp.status_code not in (200, 403):
            return []
        return _parse_tle_blocks(body)
    except (httpx.HTTPError, OSError):
        return []


async def refresh_tle(db: AsyncSession) -> int:
    """Fetch all category feeds and upsert satellites with category + orbit_class.

    Priority: specific category feeds are processed first. The `active` (OTHER)
    feed runs last so it never overwrites a more specific category already set.
    Returns total number of TLE snapshots stored.
    """
    now = datetime.now(timezone.utc)
    total = 0

    async with httpx.AsyncClient(timeout=30, headers=_HEADERS, http2=False) as client:
        for group, category in CATEGORY_FEEDS:
            blocks = await _fetch_raw(client, group)
            if not blocks:
                continue

            for name, line1, line2 in blocks:
                norad_id = int(line2[2:7])

                result = await db.execute(
                    select(Satellite).where(Satellite.norad_id == norad_id)
                )
                satellite = result.scalar_one_or_none()

                if satellite is None:
                    satellite = Satellite(
                        norad_id=norad_id,
                        name=name,
                        is_active=True,
                        category=category,
                        orbit_class=orbit_class_from_tle(line2),
                    )
                    db.add(satellite)
                else:
                    # Never downgrade a specific category to OTHER
                    if satellite.category is None or (
                        satellite.category == SatelliteCategory.OTHER
                        and category != SatelliteCategory.OTHER
                    ):
                        satellite.category = category
                    if satellite.orbit_class is None:
                        satellite.orbit_class = orbit_class_from_tle(line2)

                await db.flush()

                epoch = _parse_epoch(line1)
                db.add(
                    TleSnapshot(
                        satellite_id=satellite.id,
                        line1=line1,
                        line2=line2,
                        epoch=epoch,
                        ingested_at=now,
                    )
                )
                total += 1

            await db.commit()

            # Polite delay between CelesTrak requests
            await asyncio.sleep(0.5)

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
