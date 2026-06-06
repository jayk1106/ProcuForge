from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
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
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias="API_CORS_ORIGINS",
        description=(
            "Allowed CORS origins. Accepts a JSON list or a comma-separated "
            "string. The auth cookie requires explicit origins (browsers "
            "reject '*' on credentialed requests), so the dev default is the "
            "Next.js dev server origin."
        ),
    )

    api_v1_prefix: str = Field(
        default="/api/v1",
        validation_alias="API_V1_PREFIX",
    )

    vertex_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VERTEX_PROJECT_ID",
            "GOOGLE_PROJECT_ID",
            "GOOGLE_CLOUD_PROJECT",
        ),
        description="Google Cloud project hosting the Vertex AI reasoning engine.",
    )
    vertex_location: str = Field(
        default="us-central1",
        validation_alias=AliasChoices(
            "VERTEX_LOCATION",
            "GOOGLE_CLOUD_LOCATION",
            "GOOGLE_BUCKET_REGION",
        ),
        description="Vertex AI region (e.g. 'us-central1').",
    )
    reasoning_engine_app_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "BUYER_REASONING_ENGINE",
            "REASONING_ENGINE_APP_NAME",
        ),
        description=(
            "Fully-qualified Vertex AI reasoning engine resource name "
            "(projects/{project}/locations/{location}/reasoningEngines/{id})."
        ),
    )
    vendor_reasoning_engine_app_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VENDOR_REASONING_ENGINE",
            "VENDOR_REASONING_ENGINE_APP_NAME",
        ),
        description=(
            "Fully-qualified Vertex AI reasoning engine resource name for the vendor agent."
        ),
    )
    workflow_default_user_id: str | None = Field(
        default=None,
        validation_alias="WORKFLOW_DEFAULT_USER_ID",
        description=(
            "Fallback ADK session user id until auth is wired. Optional in "
            "development; required in non-development environments — enforce "
            "in app lifespan."
        ),
    )
    workflow_default_organization_id: str | None = Field(
        default=None,
        validation_alias="WORKFLOW_DEFAULT_ORGANIZATION_ID",
        description=(
            "Used when POST /workflow/start omits organization_id. Optional "
            "in development; required in non-development environments."
        ),
    )

    admin_user_id: str = Field(
        default="admin",
        validation_alias="ADMIN_USER_ID",
        description="Single-user admin identifier used as the JWT subject.",
    )
    admin_user_name: str = Field(
        default="",
        validation_alias="ADMIN_USER_NAME",
        description="Display name shown in the UI (e.g. 'Jay Kaneriya'). Falls back to admin_user_id when empty.",
    )
    admin_user_email: str = Field(
        default="",
        validation_alias="ADMIN_USER_EMAIL",
        description="Admin contact email. Surfaced in /auth/me for later use as workflow requester contact.",
    )
    admin_user_role: str = Field(
        default="Procurement Manager",
        validation_alias="ADMIN_USER_ROLE",
        description="Role / title shown in the UI.",
    )
    admin_org_id: str = Field(
        default="acme",
        validation_alias="ADMIN_ORG_ID",
        description="Organisation id paired with the admin user for downstream calls.",
    )
    admin_org_name: str = Field(
        default="",
        validation_alias="ADMIN_ORG_NAME",
        description="Organisation display name (e.g. 'Acme Manufacturing'). Falls back to admin_org_id when empty.",
    )
    admin_org_currency: str = Field(
        default="USD",
        validation_alias="ADMIN_ORG_CURRENCY",
        description="Default currency for workflows started by this admin.",
    )
    admin_password_hash: str = Field(
        default="",
        validation_alias="ADMIN_PASSWORD_HASH",
        description="Bcrypt hash of the admin password. Never store plaintext.",
    )
    jwt_secret: str = Field(
        default="",
        validation_alias="JWT_SECRET",
        description="HMAC secret used to sign session + ws-ticket JWTs.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    jwt_expiration_seconds: int = Field(
        default=604800,
        validation_alias="JWT_EXPIRATION_SECONDS",
        description="Session JWT lifetime in seconds. Default 7 days.",
    )
    jwt_ws_ticket_ttl_seconds: int = Field(
        default=60,
        validation_alias="JWT_WS_TICKET_TTL_SECONDS",
        description="One-shot ticket lifetime used for WebSocket handshake.",
    )
    session_cookie_name: str = Field(
        default="pf_session",
        validation_alias="SESSION_COOKIE_NAME",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["http://localhost:3000"]
            if stripped.startswith("["):
                return stripped
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_api_settings() -> APISettings:
    """Return a cached `APISettings` instance for dependency injection."""
    return APISettings()
