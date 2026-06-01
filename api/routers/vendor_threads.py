from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from api.dependencies import VendorThreadQueryServiceDep
from api.schemas.ui_dto import VendorConvoDTO, VendorThreadRowDTO

router = APIRouter(prefix="/vendor-threads", tags=["vendor-threads"])


class ThreadActionRequest(BaseModel):
    reason: str | None = None


class ThreadActionResponse(BaseModel):
    rfq_id: str
    workflow_id: str
    vendor_id: str
    status: str
    applied_at: str


@router.get(
    "",
    response_model=list[VendorThreadRowDTO],
    summary="List all vendor negotiation threads",
)
async def list_vendor_threads(
    service: VendorThreadQueryServiceDep,
    organization_id: str | None = Query(default=None, alias="organizationId"),
) -> list[VendorThreadRowDTO]:
    return await service.list_threads(organization_id)


@router.get(
    "/{rfq_id}",
    response_model=VendorConvoDTO,
    summary="Get vendor thread detail by rfq_id",
    responses={404: {"description": "Vendor thread not found."}},
)
async def get_vendor_thread(
    rfq_id: str,
    service: VendorThreadQueryServiceDep,
) -> VendorConvoDTO:
    return await service.get_thread(rfq_id)


@router.post(
    "/{rfq_id}/escalate",
    response_model=ThreadActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mark a vendor thread as ESCALATED for human review",
    responses={404: {"description": "Vendor thread not found."}},
)
async def escalate_vendor_thread(
    rfq_id: str,
    service: VendorThreadQueryServiceDep,
    body: ThreadActionRequest | None = None,
) -> ThreadActionResponse:
    reason = body.reason if body else None
    result = await service.escalate(rfq_id, reason)
    return ThreadActionResponse(**result)


@router.post(
    "/{rfq_id}/walk-away",
    response_model=ThreadActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Terminate a vendor thread (WALKED_AWAY)",
    responses={404: {"description": "Vendor thread not found."}},
)
async def walk_away_vendor_thread(
    rfq_id: str,
    service: VendorThreadQueryServiceDep,
    body: ThreadActionRequest | None = None,
) -> ThreadActionResponse:
    reason = body.reason if body else None
    result = await service.walk_away(rfq_id, reason)
    return ThreadActionResponse(**result)
