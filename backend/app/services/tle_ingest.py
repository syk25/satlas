from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satellite import Satellite, TleSnapshot

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
CELESTRAK_STATIONS_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
)


def _parse_tle_blocks(raw: str) -> list[tuple[str, str, str]]:
    """Parse raw TLE text into (name, line1, line2) tuples."""
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
    """Parse TLE epoch from line 1 into a UTC datetime."""
    epoch_str = line1[18:32].strip()
    year_2d = int(epoch_str[:2])
    year = 2000 + year_2d if year_2d < 57 else 1900 + year_2d
    day_of_year = float(epoch_str[2:])
    day = int(day_of_year)
    frac = day_of_year - day
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    from datetime import timedelta

    return base + timedelta(days=day - 1) + timedelta(days=frac)


async def fetch_and_store_tle(db: AsyncSession, url: str = CELESTRAK_URL) -> int:
    """Fetch TLE data from CelesTrak and upsert satellites + snapshots.

    Returns the number of satellites processed.
    """
    headers = {"User-Agent": "satlas/0.1 (https://github.com/syk25/satlas)"}
    async with httpx.AsyncClient(timeout=30, headers=headers, http2=False) as client:
        response = await client.get(url)

    # CelesTrak returns 403 + plain-text notice when data hasn't changed
    body = response.text
    if "GP data has not updated" in body:
        return 0

    if response.status_code not in (200, 403):
        response.raise_for_status()

    blocks = _parse_tle_blocks(body)
    now = datetime.now(timezone.utc)
    count = 0

    for name, line1, line2 in blocks:
        norad_id = int(line2[2:7])

        # Upsert satellite
        result = await db.execute(
            select(Satellite).where(Satellite.norad_id == norad_id)
        )
        satellite = result.scalar_one_or_none()
        if satellite is None:
            satellite = Satellite(norad_id=norad_id, name=name, is_active=True)
            db.add(satellite)
            await db.flush()

        # Store TLE snapshot
        epoch = _parse_epoch(line1)
        snapshot = TleSnapshot(
            satellite_id=satellite.id,
            line1=line1,
            line2=line2,
            epoch=epoch,
            ingested_at=now,
        )
        db.add(snapshot)
        count += 1

    await db.commit()
    return count


async def get_latest_tle_snapshots(
    db: AsyncSession,
) -> list[tuple[Satellite, TleSnapshot]]:
    """Return the most recent TLE snapshot for each active satellite."""
    from sqlalchemy import func

    subq = (
        select(
            TleSnapshot.satellite_id,
            func.max(TleSnapshot.ingested_at).label("max_ingested"),
        )
        .group_by(TleSnapshot.satellite_id)
        .subquery()
    )

    result = await db.execute(
        select(Satellite, TleSnapshot)
        .join(TleSnapshot, Satellite.id == TleSnapshot.satellite_id)
        .join(
            subq,
            (TleSnapshot.satellite_id == subq.c.satellite_id)
            & (TleSnapshot.ingested_at == subq.c.max_ingested),
        )
        .where(Satellite.is_active == True)  # noqa: E712
    )
    return result.all()
