from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.workflow import WorkflowStartRequest, WorkflowStartResponse
from db.collections.product import Product
from db.firestore.repositories.products import ProductRepository

logger = logging.getLogger(__name__)


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

        await self._create_session(workflow_id, user_id, request, product)

        response = WorkflowStartResponse(
            workflow_id=workflow_id,
            session_id=workflow_id,
            started_at=datetime.now(timezone.utc),
        )
        job = AgentJob(
            workflow_id=workflow_id,
            user_id=user_id,
            prompt=self._build_prompt(request, product),
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

            session_service = VertexAiSessionService(
                project=self._settings.vertex_project_id,
                location=self._settings.vertex_location,
            )
            runner = Runner(
                agent=root_agent,
                app_name=self._settings.reasoning_engine_app_name,
                session_service=session_service,
            )
            logger.info("prompt", extra={"prompt": job.prompt})
            print("prompt", job.prompt)
            message = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=job.prompt)],
            )

            logger.info("workflow.run.start")
            for event in runner.run(
                user_id=job.user_id,
                session_id=job.workflow_id,
                new_message=message,
            ):
                if event.is_final_response():
                    logger.info(
                        "workflow.run.final",
                        extra={"workflow_id": job.workflow_id},
                    )
            logger.info("workflow.run.complete", extra={"workflow_id": job.workflow_id})
        except Exception:
            logger.exception(
                "workflow.run.failed", extra={"workflow_id": job.workflow_id}
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

    async def _create_session(
        self,
        workflow_id: str,
        user_id: str,
        request: WorkflowStartRequest,
        product: Product,
    ) -> None:
        from google.adk.sessions import VertexAiSessionService

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        try:
            await session_service.create_session(
                app_name=self._settings.reasoning_engine_app_name,
                user_id=user_id,
                session_id=workflow_id,
                state={
                    "request": request.model_dump(mode="json"),
                    "product": product.model_dump(mode="json", by_alias=True),
                },
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
    def _build_prompt(request: WorkflowStartRequest, product: Product) -> str:
        loc = request.delivery_location
        notes = (
            "\n- " + "\n- ".join(request.buyer_notes)
            if request.buyer_notes
            else " (none)"
        )
        return (
            "Initiate a procurement workflow with the following parameters:\n"
            f"- Product: {product.name} (id={product.id}, brand={product.brand})\n"
            f"- Quantity: {request.quantity}\n"
            f"- Required by: {request.required_by.isoformat()}\n"
            f"- Urgency: {request.urgency.value}\n"
            f"- Budget ceiling: {request.budget_ceiling} {request.currency}\n"
            f"- Delivery location: {loc.address}, {loc.city}, {loc.state}, "
            f"{loc.country} - {loc.pincode}\n"
            f"- Buyer notes:{notes}\n\n"
            "Begin by searching for suitable vendors, then proceed with the standard "
            "negotiation, decision, purchase order and verification stages."
        )
