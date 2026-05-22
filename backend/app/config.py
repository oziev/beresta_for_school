"""Application configuration from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from `.env` / process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Beresta", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")

    database_url: str = Field(
        default="postgresql+asyncpg://beresta:beresta@localhost:5432/beresta",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # GigaChat (Sber); exact auth shape is implemented in later stages
    gigachat_api_key: str | None = Field(default=None, alias="GIGACHAT_API_KEY")
    gigachat_client_id: str | None = Field(default=None, alias="GIGACHAT_CLIENT_ID")
    gigachat_client_secret: str | None = Field(default=None, alias="GIGACHAT_CLIENT_SECRET")
    gigachat_scope: str = Field(default="GIGACHAT_API_PERS", alias="GIGACHAT_SCOPE")
    gigachat_base_url: str = Field(
        default="https://gigachat.devices.sberbank.ru/api/v1",
        alias="GIGACHAT_BASE_URL",
    )
    gigachat_oauth_url: str = Field(
        default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        alias="GIGACHAT_OAUTH_URL",
    )
    gigachat_model: str = Field(default="GigaChat", alias="GIGACHAT_MODEL")
    # Optional: готовая строка `Basic <base64>` или только base64(client_id:client_secret)
    gigachat_authorization_key: str | None = Field(default=None, alias="GIGACHAT_AUTHORIZATION_KEY")

    # Локальная разработка без ключей: детерминированные задания вместо GigaChat
    beresta_llm_stub: bool = Field(default=False, alias="BERESTA_LLM_STUB")

    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000",
        alias="CORS_ORIGINS",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    # LLM / cache defaults (used from stage 2 onward)
    llm_timeout_sec: float = Field(default=30.0, alias="LLM_TIMEOUT_SEC")
    llm_cache_ttl_sec: int = Field(default=3600, alias="LLM_CACHE_TTL_SEC")
    redis_session_ttl_sec: int = Field(default=86400, alias="REDIS_SESSION_TTL_SEC")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
