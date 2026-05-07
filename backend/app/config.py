from pathlib import Path

from pydantic_settings import BaseSettings

# .env is at the monorepo root (two levels above this file)
_env_file = Path(__file__).parents[2] / ".env"


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str
    test_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]

    model_config = {"env_file": str(_env_file)}

    @property
    def async_database_url(self) -> str:
        # Fly injects postgres:// with ?sslmode=disable; asyncpg needs postgresql+asyncpg://
        url = self.database_url.replace(
            "postgres://", "postgresql+asyncpg://", 1
        ).replace("postgresql://", "postgresql+asyncpg://", 1)
        return url.replace("?sslmode=disable", "").replace("&sslmode=disable", "")


settings = Settings()
