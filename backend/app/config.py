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

    model_config = {"env_file": str(_env_file)}


settings = Settings()
