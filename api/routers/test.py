from __future__ import annotations

from fastapi import APIRouter, status

from api.schemas.common import EchoRequest, EchoResponse, PingResponse

router = APIRouter(prefix="/test", tags=["test"])


@router.get(
    "/ping",
    response_model=PingResponse,
    status_code=status.HTTP_200_OK,
    summary="Ping the API",
)
async def ping() -> PingResponse:
    return PingResponse()


@router.post(
    "/echo",
    response_model=EchoResponse,
    status_code=status.HTTP_200_OK,
    summary="Echo a payload back to the caller",
)
async def echo(payload: EchoRequest) -> EchoResponse:
    return EchoResponse(message=payload.message, metadata=payload.metadata)
