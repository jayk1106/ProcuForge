from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.buyer_workflow_session import BuyerWorkflowSessionState
from api.schemas.workflow import (
    BuyerSessionRequestState,
    WorkflowStartRequest,
    WorkflowStartResponse,
)
from db.collections.product import Product
from db.firestore.repositories.products import ProductRepository

logger = logging.getLogger(__name__)


def _truncate_prompt_preview(text: str, *, max_len: int = 400) -> str:
    """Shorten prompt text for debug logs (single line, ellipsis if needed)."""
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


@dataclass(slots=True)
class AgentJob:
    """Payload handed to the background runner after the response is sent."""

    workflow_id: str
    user_id: str
    prompt: str


class WorkflowService:
    """Coordinates input validation, ADK session creation, and runner kickoff."""

    def __init__(self, product_repo: ProductRepository, settings: APISettings) -> None:
        self._product_repo = product_repo
        self._settings = settings

    async def start(
        self, request: WorkflowStartRequest
    ) -> tuple[WorkflowStartResponse, AgentJob]:
        self._ensure_vertex_configured()

        product = await self._validate_product(request.product_id)

        workflow_id = str(uuid.uuid4())
        user_id = self._settings.workflow_default_user_id
        started_at = datetime.now(timezone.utc)
        organization_id = self._resolve_organization_id(request)
        requester_id = (request.requester_id or self._settings.workflow_default_user_id).strip()
        buyer_request = BuyerSessionRequestState.from_workflow_start(
            workflow_id=workflow_id,
            created_at=started_at,
            body=request,
            organization_id=organization_id,
            requester_id=requester_id,
        )

        await self._create_session(workflow_id, user_id, buyer_request, product)

        response = WorkflowStartResponse(
            workflow_id=workflow_id,
            session_id=workflow_id,
            started_at=started_at,
        )
        job = AgentJob(
            workflow_id=workflow_id,
            user_id=user_id,
            prompt=self._build_kickoff_prompt(buyer_request.request_id),
        )
        return response, job

    def run_agent(self, job: AgentJob) -> None:
        """Run the buyer agent synchronously. Invoked by FastAPI BackgroundTasks
        on the thread pool, so the synchronous ADK iterator does not block the loop.
        """
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import VertexAiSessionService
            from google.genai import types as genai_types

            from procu_forge_buyer.agent import root_agent

            logger.info(
                "workflow.run.start workflow_id=%s user_id=%s prompt_chars=%s",
                job.workflow_id,
                job.user_id,
                len(job.prompt),
            )
            logger.debug(
                "workflow.run.prompt_preview workflow_id=%s %s",
                job.workflow_id,
                _truncate_prompt_preview(job.prompt, max_len=400),
            )

            session_service = VertexAiSessionService(
                project=self._settings.vertex_project_id,
                location=self._settings.vertex_location,
            )
            runner = Runner(
                agent=root_agent,
                app_name=self._settings.reasoning_engine_app_name,
                session_service=session_service,
            )
            message = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=job.prompt)],
            )

            for event in runner.run(
                user_id=job.user_id,
                session_id=job.workflow_id,
                new_message=message,
            ):
                if logger.isEnabledFor(logging.DEBUG):
                    is_final = (
                        event.is_final_response()
                        if hasattr(event, "is_final_response")
                        else False
                    )
                    logger.debug(
                        "workflow.run.event workflow_id=%s type=%s is_final=%s",
                        job.workflow_id,
                        type(event).__name__,
                        is_final,
                    )
                if hasattr(event, "is_final_response") and event.is_final_response():
                    logger.info(
                        "workflow.run.final_response workflow_id=%s",
                        job.workflow_id,
                    )

            logger.info("workflow.run.complete workflow_id=%s", job.workflow_id)
        except Exception:
            logger.exception(
                "workflow.run.failed workflow_id=%s",
                job.workflow_id,
            )

    async def _validate_product(self, product_id: str) -> Product:
        product = await self._product_repo.get(product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{product_id}' not found.",
            )
        if not product.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product '{product_id}' is inactive and cannot be procured.",
            )
        return product

    def _resolve_organization_id(self, request: WorkflowStartRequest) -> str:
        org = request.organization_id or self._settings.workflow_default_organization_id
        if not org or not org.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "organization_id is required unless WORKFLOW_DEFAULT_ORGANIZATION_ID "
                    "is configured."
                ),
            )
        return org.strip()

    async def _create_session(
        self,
        workflow_id: str,
        user_id: str,
        buyer_request: BuyerSessionRequestState,
        product: Product,
    ) -> None:
        from google.adk.sessions import VertexAiSessionService

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        session_state = BuyerWorkflowSessionState(
            request=buyer_request,
            product=product,
        ).to_vertex_state()
        try:
            await session_service.create_session(
                app_name=self._settings.reasoning_engine_app_name,
                user_id=user_id,
                session_id=workflow_id,
                state=session_state,
            )
        except Exception as exc:
            logger.exception(
                "workflow.session.create_failed",
                extra={"workflow_id": workflow_id},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to initialise the agent session. Please retry.",
            ) from exc

    def _ensure_vertex_configured(self) -> None:
        missing: list[str] = []
        if not self._settings.vertex_project_id:
            missing.append("VERTEX_PROJECT_ID/GOOGLE_PROJECT_ID")
        if not self._settings.reasoning_engine_app_name:
            missing.append("REASONING_ENGINE_APP_NAME")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Workflow runtime is not configured. Missing env vars: "
                    + ", ".join(missing)
                ),
            )

    @staticmethod
    def _build_kickoff_prompt(request_id: str) -> str:
        return (
            f"Start procurement workflow {request_id}. "
            "Use session state for all parameters (request, product); do not ask the user "
            "to repeat them unless something is missing from state."
        )
