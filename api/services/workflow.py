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
    WorkflowApproveResponse,
    WorkflowResolveEscalationResponse,
    WorkflowStartRequest,
    WorkflowStartResponse,
)
from db.collections.product import Product
from db.firestore.repositories.products import ProductRepository
from procu_forge_buyer.pr_status import PrStatus

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

    def __init__(
        self,
        product_repo: ProductRepository,
        settings: APISettings,
    ) -> None:
        self._product_repo = product_repo
        self._settings = settings

    async def start(
        self, request: WorkflowStartRequest
    ) -> tuple[WorkflowStartResponse, AgentJob]:
        self._ensure_vertex_configured()

        product = await self._validate_product(request.product_id)

        workflow_id = str(uuid.uuid4())
        user_id = self._settings.workflow_default_user_id or ""
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WORKFLOW_DEFAULT_USER_ID is not configured.",
            )
        started_at = datetime.now(timezone.utc)
        organization_id = self._resolve_organization_id(request)
        requester_id = (request.requester_id or user_id).strip()
        buyer_request = BuyerSessionRequestState.from_workflow_start(
            workflow_id=workflow_id,
            created_at=started_at,
            body=request,
            organization_id=organization_id,
            requester_id=requester_id,
        )

        initial_state = await self._create_session(
            workflow_id,
            user_id,
            buyer_request,
            product,
            approval_required=request.approval_required,
        )

        # Seed the Firestore workflow_state row immediately from the initial
        # state we just wrote, so the flows list reflects the new flow before
        # the first agent state_delta. Direct projection avoids a Vertex
        # eventual-consistency race that a broadcast-driven factory would hit.
        from api.services.state_projection import project_workflow_state

        await project_workflow_state(workflow_id, initial_state)

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

        Every event the Runner emits with a non-empty ``actions.state_delta`` is
        a buyer state mutation. After each such event we schedule a debounced
        ``state_changed`` broadcast on the workflow channel; the connection
        manager collapses bursts and dedupes identical DTOs.
        """
        from api.services.workflow_query import build_workflow_detail
        from api.ws import broadcast_state

        def _emit_state(reason: str) -> None:
            broadcast_state(
                job.workflow_id,
                lambda: build_workflow_detail(job.workflow_id),
                reason=reason,
                workflow_id=job.workflow_id,
            )

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
                actions = getattr(event, "actions", None)
                state_delta = getattr(actions, "state_delta", None) if actions else None
                if state_delta:
                    logger.debug(
                        "workflow.run.state_delta workflow_id=%s keys=%s",
                        job.workflow_id,
                        list(state_delta.keys()),
                    )
                    _emit_state("runner_state_delta")

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

            # Safety: catch any nested mutations that didn't surface as a
            # top-level state_delta on the events we observed.
            _emit_state("runner_complete")
            logger.info("workflow.run.complete workflow_id=%s", job.workflow_id)
        except Exception:
            logger.exception(
                "workflow.run.failed workflow_id=%s",
                job.workflow_id,
            )

    async def approve(
        self, workflow_id: str
    ) -> tuple[WorkflowApproveResponse, AgentJob]:
        """Approve a parked workflow and advance pr_status to the resume value.

        Infers which step is being approved from the current ``pr_status``:
        ``AWAITING_PO_APPROVAL`` → step ``po``, resume ``VENDOR_SELECTED``;
        ``AWAITING_GRN_APPROVAL`` → step ``grn``, resume ``PO_ACKNOWLEDGED``;
        ``AWAITING_COMPLETION_APPROVAL`` → step ``completion``, resume
        ``INVOICE_UNDER_VERIFICATION``. Records the step in
        ``approved_steps`` so the gating callback will not re-park on this
        step, clears ``pending_approval``, and queues an agent re-run.
        """
        from datetime import datetime, timezone

        from google.adk.events.event import Event
        from google.adk.events.event_actions import EventActions
        from google.adk.sessions import VertexAiSessionService

        from procu_forge_buyer.pr_status import PrStatus
        from procu_forge_buyer.state_keys import (
            APPROVED_STEPS_KEY,
            PENDING_APPROVAL_KEY,
            PR_STATUS_KEY,
            PREVIOUS_PR_STATUS_KEY,
        )

        resume_table: dict[str, tuple[str, str]] = {
            PrStatus.AWAITING_PO_APPROVAL.value: ("po", PrStatus.VENDOR_SELECTED.value),
            PrStatus.AWAITING_GRN_APPROVAL.value: ("grn", PrStatus.PO_ACKNOWLEDGED.value),
            PrStatus.AWAITING_COMPLETION_APPROVAL.value: (
                "completion",
                PrStatus.INVOICE_UNDER_VERIFICATION.value,
            ),
            # Legacy alias: pre-HITL sessions parked here go straight to PO_ISSUED
            # (the old behavior).
            PrStatus.AWAITING_USER_APPROVAL.value: ("po", PrStatus.PO_ISSUED.value),
        }

        self._ensure_vertex_configured()

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        user_id = self._settings.workflow_default_user_id or ""
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WORKFLOW_DEFAULT_USER_ID is not configured.",
            )

        session = await session_service.get_session(
            app_name=self._settings.reasoning_engine_app_name,
            user_id=user_id,
            session_id=workflow_id,
        )
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )

        current_status = session.state.get(PR_STATUS_KEY)
        resume = resume_table.get(str(current_status) if current_status else "")
        if resume is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Workflow is not awaiting approval. "
                    f"Current status: {current_status!r}"
                ),
            )
        step, resume_status = resume

        existing_approved = session.state.get(APPROVED_STEPS_KEY) or []
        if not isinstance(existing_approved, list):
            existing_approved = []
        if step not in existing_approved:
            next_approved = list(existing_approved) + [step]
        else:
            next_approved = list(existing_approved)

        state_event = Event(
            invocation_id=f"approve-{uuid.uuid4().hex}",
            author="api:approve",
            actions=EventActions(
                state_delta={
                    PREVIOUS_PR_STATUS_KEY: current_status,
                    PR_STATUS_KEY: resume_status,
                    APPROVED_STEPS_KEY: next_approved,
                    PENDING_APPROVAL_KEY: None,
                }
            ),
        )
        await session_service.append_event(session, state_event)

        from api.services.workflow_query import build_workflow_detail
        from api.ws import broadcast_state

        broadcast_state(
            workflow_id,
            lambda: build_workflow_detail(workflow_id),
            reason="approve",
            workflow_id=workflow_id,
        )

        approved_at = datetime.now(timezone.utc)

        logger.info(
            "workflow.approve  workflow_id=%s step=%s status=%s->%s",
            workflow_id, step, current_status, resume_status,
        )

        response = WorkflowApproveResponse(workflow_id=workflow_id, approved_at=approved_at)
        job = AgentJob(
            workflow_id=workflow_id,
            user_id=user_id,
            prompt=(
                f"Continue procurement workflow {workflow_id}. "
                f"The {step} step has been approved — proceed with purchase_manager_agent."
            ),
        )
        return response, job

    async def resolve_escalation(
        self, workflow_id: str
    ) -> tuple[WorkflowResolveEscalationResponse, AgentJob | None]:
        """Restore pr_status after full-tier ESCALATED and re-kick the agent."""
        from google.adk.events.event import Event
        from google.adk.events.event_actions import EventActions
        from google.adk.sessions import VertexAiSessionService

        from procu_forge_buyer.pr_status import PrStatus
        from procu_forge_buyer.pr_status_transitions import transition_resume_for_escalated
        from procu_forge_buyer.state_keys import (
            ESCALATION_CONTEXT_KEY,
            ESCALATION_EMAIL_SENT_AT_KEY,
            ESCALATION_PENDING_NOTIFY_KEY,
            PR_STATUS_KEY,
            PREVIOUS_PR_STATUS_KEY,
        )

        self._ensure_vertex_configured()

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        user_id = self._settings.workflow_default_user_id or ""
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WORKFLOW_DEFAULT_USER_ID is not configured.",
            )

        session = await session_service.get_session(
            app_name=self._settings.reasoning_engine_app_name,
            user_id=user_id,
            session_id=workflow_id,
        )
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )

        state = session.state if isinstance(session.state, dict) else {}
        current_status = str(state.get(PR_STATUS_KEY) or "")

        if current_status != PrStatus.ESCALATED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Workflow is not in ESCALATED status. Current status: {current_status!r}"
                ),
            )

        mutable = dict(state)
        if not transition_resume_for_escalated(mutable):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot resolve escalation — previous pr_status missing.",
            )
        resume_status = str(mutable.get(PR_STATUS_KEY) or "")

        resolved_at = datetime.now(timezone.utc)
        state_event = Event(
            invocation_id=f"resolve-escalation-{uuid.uuid4().hex}",
            author="api:resolve_escalation",
            actions=EventActions(
                state_delta={
                    PR_STATUS_KEY: resume_status,
                    PREVIOUS_PR_STATUS_KEY: PrStatus.ESCALATED.value,
                    ESCALATION_CONTEXT_KEY: None,
                    ESCALATION_PENDING_NOTIFY_KEY: False,
                    ESCALATION_EMAIL_SENT_AT_KEY: None,
                }
            ),
        )
        await session_service.append_event(session, state_event)

        from api.services.workflow_query import build_workflow_detail
        from api.ws import broadcast_state

        broadcast_state(
            workflow_id,
            lambda: build_workflow_detail(workflow_id),
            reason="resolve_escalation",
            workflow_id=workflow_id,
        )

        response = WorkflowResolveEscalationResponse(
            workflow_id=workflow_id,
            resolved_at=resolved_at,
            resumed_pr_status=resume_status or None,
        )
        job = AgentJob(
            workflow_id=workflow_id,
            user_id=user_id,
            prompt=(
                f"Continue procurement workflow {workflow_id}. "
                f"Escalation was resolved — resume from pr_status {resume_status}."
            ),
        )
        return response, job

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
        *,
        approval_required: bool = False,
    ) -> dict:
        from google.adk.sessions import VertexAiSessionService

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        session_state = BuyerWorkflowSessionState(
            request=buyer_request,
            product=product,
            approval_required=approval_required,
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
        return session_state

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

