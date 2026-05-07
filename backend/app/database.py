from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_db_url = settings.async_database_url
# Fly internal network (.flycast / .internal) doesn't support TLS on asyncpg
_connect_args = (
    {"ssl": False} if any(h in _db_url for h in ("flycast", ".internal")) else {}
)

engine = create_async_engine(
    _db_url,
    echo=settings.environment == "development",
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
