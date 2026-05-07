from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status

from api.dependencies import WorkflowServiceDep
from api.schemas.workflow import WorkflowStartRequest, WorkflowStartResponse

router = APIRouter(prefix="/workflow", tags=["workflow"])


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
