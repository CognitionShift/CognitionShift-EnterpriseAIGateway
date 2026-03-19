"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "CognitionShift Enterprise AI Gateway"
    debug: bool = False
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://csgateway:csgateway@postgres:5432/csgateway"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Auth / JWT
    secret_key: str = "CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_hours: int = 8

    # Anthropic
    anthropic_api_key: str = ""

    # OpenAI (optional)
    openai_api_key: str = ""

    # Google Gemini (optional)
    google_api_key: str = ""

    # Google OAuth (Drive integration)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://10.1.1.112:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
