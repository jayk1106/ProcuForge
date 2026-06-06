from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from api.config import APISettings, get_api_settings
from api.schemas.common import HealthResponse
from db.firestore.client import get_firestore_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

SettingsDep = Annotated[APISettings, Depends(get_api_settings)]

_VENDOR_AGENT_CARD_PATH = "/.well-known/agent-card.json"


def _vendor_agent_card_url() -> str:
    host = os.getenv("VENDOR_SERVER_HOST", "127.0.0.1").strip()
    port = os.getenv("VENDOR_SERVER_PORT", "8001").strip()
    explicit = os.getenv("VENDOR_A2A_AGENT_CARD_URL", "").strip()
    if explicit:
        return explicit
    return f"http://{host}:{port}{_VENDOR_AGENT_CARD_PATH}"


def _production_config_errors(settings: APISettings) -> list[str]:
    if settings.environment == "development":
        return []
    missing: list[str] = []
    if not settings.vertex_project_id:
        missing.append("GOOGLE_CLOUD_PROJECT")
    if not settings.reasoning_engine_app_name:
        missing.append("BUYER_REASONING_ENGINE")
    if not settings.vendor_reasoning_engine_app_name:
        missing.append("VENDOR_REASONING_ENGINE")
    return missing


def _check_vendor_agent_card() -> str | None:
    url = _vendor_agent_card_url()
    try:
        with urlopen(url, timeout=2) as response:
            if response.status >= 400:
                return f"vendor A2A agent card returned HTTP {response.status}"
    except URLError as exc:
        return f"vendor A2A agent card unreachable at {url}: {exc.reason}"
    except OSError as exc:
        return f"vendor A2A agent card unreachable at {url}: {exc}"
    return None


def _check_firestore() -> str | None:
    try:
        client = get_firestore_client()
        list(client.collections(page_size=1))
    except Exception as exc:
        logger.warning("health.ready.firestore_failed detail=%s", exc)
        return f"Firestore unreachable: {exc}"
    return None


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health",
)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )


@router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
)
async def live(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
)
async def ready(settings: SettingsDep) -> HealthResponse | JSONResponse:
    failures: list[str] = []

    failures.extend(_production_config_errors(settings))

    firestore_error = await asyncio.to_thread(_check_firestore)
    if firestore_error:
        failures.append(firestore_error)

    vendor_error = await asyncio.to_thread(_check_vendor_agent_card)
    if vendor_error:
        failures.append(vendor_error)

    if failures:
        body = HealthResponse(
            status="error",
            environment=settings.environment,
            version=settings.app_version,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                **body.model_dump(mode="json"),
                "detail": failures,
            },
        )

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )
