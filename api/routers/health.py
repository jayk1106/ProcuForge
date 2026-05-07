from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from api.config import APISettings, get_api_settings
from api.schemas.common import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])

SettingsDep = Annotated[APISettings, Depends(get_api_settings)]


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
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
)
async def ready(settings: SettingsDep) -> HealthResponse:
    # Readiness should fail when downstream deps (Firestore, etc.) aren't reachable.
    # Wire those checks here as services are added.
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )
