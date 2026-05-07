from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(
        default="ProcuForge API",
        validation_alias="API_APP_NAME",
    )
    app_version: str = Field(
        default="0.1.0",
        validation_alias="API_APP_VERSION",
    )
    app_description: str = Field(
        default="ProcuForge HTTP API.",
        validation_alias="API_APP_DESCRIPTION",
    )

    environment: str = Field(
        default="development",
        validation_alias="API_ENV",
    )
    debug: bool = Field(
        default=False,
        validation_alias="API_DEBUG",
    )

    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        validation_alias="API_CORS_ORIGINS",
        description=(
            "Allowed CORS origins. Accepts a JSON list or a comma-separated "
            "string in the environment variable."
        ),
    )

    api_v1_prefix: str = Field(
        default="/api/v1",
        validation_alias="API_V1_PREFIX",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["*"]
            if stripped.startswith("["):
                return stripped
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_api_settings() -> APISettings:
    """Return a cached `APISettings` instance for dependency injection."""
    return APISettings()
