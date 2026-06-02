from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from api.dependencies import VendorThreadQueryServiceDep, WorkflowQueryServiceDep, WorkflowServiceDep
from api.schemas.ui_dto import VendorConvoDTO, VendorThreadRowDTO, WorkflowDetailDTO, WorkflowRowDTO
from api.schemas.workflow import WorkflowApproveResponse, WorkflowStartRequest, WorkflowStartResponse

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get(
    "/list",
    response_model=list[WorkflowRowDTO],
    summary="List procurement workflows",
)
async def list_workflows(
    service: WorkflowQueryServiceDep,
    organization_id: str | None = Query(default=None, alias="organizationId"),
) -> list[WorkflowRowDTO]:
    return await service.list_workflows(organization_id)


@router.get(
    "/{workflow_id}/state",
    summary="Get raw buyer session state for debugging",
    responses={404: {"description": "Workflow not found."}},
)
async def get_workflow_state(
    workflow_id: str,
    service: WorkflowQueryServiceDep,
) -> dict:
    state = await service.get_workflow_state(workflow_id)
    if not state:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")
    return state


@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailDTO,
    summary="Get workflow detail",
    responses={404: {"description": "Workflow not found."}},
)
async def get_workflow(
    workflow_id: str,
    service: WorkflowQueryServiceDep,
) -> WorkflowDetailDTO:
    return await service.get_workflow(workflow_id)


@router.post(
    "/start",
    response_model=WorkflowStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a procurement workflow",
    responses={
        404: {"description": "Product not found."},
        422: {"description": "Validation failed (payload or product inactive)."},
        502: {"description": "Failed to initialise the agent session."},
        503: {"description": "Workflow runtime is not configured."},
    },
)
async def start_workflow(
    payload: WorkflowStartRequest,
    background_tasks: BackgroundTasks,
    service: WorkflowServiceDep,
) -> WorkflowStartResponse:
    """Validate the procurement request, create the agent session, and kick off
    the buyer agent run as a background task.
    """
    response, job = await service.start(payload)
    background_tasks.add_task(service.run_agent, job)
    return response


@router.post(
    "/{workflow_id}/approve",
    response_model=WorkflowApproveResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Approve a workflow at AWAITING_USER_APPROVAL and issue the PO",
    responses={
        404: {"description": "Workflow not found."},
        422: {"description": "Workflow is not awaiting approval."},
        503: {"description": "Workflow runtime is not configured."},
    },
)
async def approve_workflow(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    service: WorkflowServiceDep,
) -> WorkflowApproveResponse:
    """Advance the workflow from AWAITING_USER_APPROVAL to PO_ISSUED and
    resume the buyer agent loop to send the Purchase Order.
    """
    response, job = await service.approve(workflow_id)
    background_tasks.add_task(service.run_agent, job)
    return response
