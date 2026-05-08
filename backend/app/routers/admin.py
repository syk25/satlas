import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.tle_ingest import ingest_feed

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
    """Receive CelesTrak GP JSON from GitHub Actions and upsert to DB.

    GitHub Actions runners use non-datacenter IPs not blocked by CelesTrak,
    so they fetch the data and push it here instead of the server pulling it.
    The JSON format includes COUNTRY_CODE and LAUNCH_DATE alongside TLE lines.
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
