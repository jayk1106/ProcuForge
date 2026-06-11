from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from api.dependencies import (
    VendorThreadQueryServiceDep,
    WorkflowQueryServiceDep,
    WorkflowServiceDep,
    get_current_admin,
)
from api.schemas.ui_dto import (
    PagedWorkflowRows,
    VendorConvoDTO,
    VendorThreadRowDTO,
    WorkflowDetailDTO,
    WorkflowRowDTO,
)
from api.schemas.workflow import WorkflowApproveResponse, WorkflowResolveEscalationResponse, WorkflowStartRequest, WorkflowStartResponse

router = APIRouter(
    prefix="/workflow",
    tags=["workflow"],
    dependencies=[Depends(get_current_admin)],
)


@router.get(
    "/list",
    response_model=PagedWorkflowRows,
    summary="List procurement workflows (cursor-paginated)",
)
async def list_workflows(
    service: WorkflowQueryServiceDep,
    organization_id: str | None = Query(default=None, alias="organizationId"),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None),
    status_filter: Literal["all", "progress", "action", "completed", "walked"] = Query(
        default="all", alias="status",
    ),
) -> PagedWorkflowRows:
    return await service.list_workflows(
        organization_id, limit=limit, cursor=cursor, status_filter=status_filter,
    )


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
    summary="Approve a workflow parked at an HITL gate",
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
    """Resume a workflow parked at one of the human-in-the-loop gates.

    The step being approved is inferred from the current ``pr_status``:
    ``AWAITING_PO_APPROVAL``, ``AWAITING_GRN_APPROVAL``,
    ``AWAITING_COMPLETION_APPROVAL``, or the legacy
    ``AWAITING_USER_APPROVAL``. The endpoint flips ``pr_status`` back to the
    matching active value and re-runs the buyer agent so ``purchase_manager``
    can send the corresponding document.
    """
    response, job = await service.approve(workflow_id)
    background_tasks.add_task(service.run_agent, job)
    return response


@router.post(
    "/{workflow_id}/resolve-escalation",
    response_model=WorkflowResolveEscalationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resolve a full-tier workflow escalation and resume the agent",
    responses={
        404: {"description": "Workflow not found."},
        422: {"description": "Workflow is not in a resolvable escalation state."},
        503: {"description": "Workflow runtime is not configured."},
    },
)
async def resolve_workflow_escalation(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    service: WorkflowServiceDep,
) -> WorkflowResolveEscalationResponse:
    response, job = await service.resolve_escalation(workflow_id)
    if job is not None:
        background_tasks.add_task(service.run_agent, job)
    return response
