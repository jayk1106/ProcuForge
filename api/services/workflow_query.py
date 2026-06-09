"""List and detail queries for buyer workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.ui_dto import WorkflowDetailDTO, WorkflowRowDTO
from api.services.session_reader import BuyerSessionReader
from api.services.status_mapping import (
    needs_action,
    parse_pr_status,
    pr_status_human_label,
)
from api.services.ui_mappers import workflow_detail_from_state, workflow_row_from_state
from db.collections.workflow_index import WorkflowIndexEntry
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from db.firestore.repositories.workflow_index import WorkflowIndexRepository
from procu_forge_buyer.state_keys import (
    NEGOTIATION_CONFIG_KEY,
    PR_STATUS_KEY,
    REQUEST_KEY,
    VENDOR_OFFERS_KEY,
)

logger = logging.getLogger(__name__)


class WorkflowQueryService:
    def __init__(
        self,
        settings: APISettings,
        index_repo: WorkflowIndexRepository,
        vendor_repo: VendorRepository,
        events_repo: WorkflowEventsRepository,
    ) -> None:
        self._settings = settings
        self._index_repo = index_repo
        self._vendor_repo = vendor_repo
        self._events_repo = events_repo
        self._buyer_reader = BuyerSessionReader(settings)

    def _ensure_configured(self) -> None:
        if not self._settings.vertex_project_id or not self._settings.reasoning_engine_app_name:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Buyer workflow runtime is not configured.",
            )

    async def list_workflows(self, organization_id: str | None = None) -> list[WorkflowRowDTO]:
        self._ensure_configured()
        org = organization_id or self._settings.workflow_default_organization_id
        if not org:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required.",
            )
        entries = await self._index_repo.list_by_org(org)
        now = datetime.now(timezone.utc)
        return [
            WorkflowRowDTO(
                id=e.workflow_id,
                requestId=e.request_id,
                product=e.product_name,
                requestedBy=e.requester_id,
                requestedAt=e.started_at.date().isoformat(),
                phase=_index_phase(e.pr_status),  # type: ignore[arg-type]
                currentState=pr_status_human_label(parse_pr_status(e.pr_status)),
                vendors=e.vendor_count,
                days=max(
                    0,
                    (
                        now
                        - (
                            e.started_at.replace(tzinfo=timezone.utc)
                            if e.started_at.tzinfo is None
                            else e.started_at
                        )
                    ).days,
                ),
                needsAction=e.needs_action,
                actionLabel=_index_action_label(e.pr_status) if e.needs_action else None,
                walked=e.pr_status in {"NO_VENDOR_AVAILABLE", "NO_VENDORS_DISCOVERED"},
            )
            for e in entries
        ]

    async def get_workflow(self, workflow_id: str) -> WorkflowDetailDTO:
        self._ensure_configured()
        session = await self._buyer_reader.get_session(workflow_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )
        state = session.state if isinstance(session.state, dict) else {}

        await self._lazy_upsert_index(workflow_id, state)

        return await _assemble_workflow_detail(
            workflow_id,
            state,
            vendor_repo=self._vendor_repo,
            events_repo=self._events_repo,
        )

    async def get_workflow_state(self, workflow_id: str) -> dict:
        """Return raw session state for vendor-thread flattening."""
        self._ensure_configured()
        session = await self._buyer_reader.get_session(workflow_id)
        if session is None:
            return {}
        return session.state if isinstance(session.state, dict) else {}

    async def _lazy_upsert_index(self, workflow_id: str, state: dict) -> None:
        request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
        product = state.get("product") if isinstance(state.get("product"), dict) else {}
        pr_status = parse_pr_status(state.get(PR_STATUS_KEY))

        vendor_count = 0
        neg = state.get(NEGOTIATION_CONFIG_KEY)
        if isinstance(neg, dict):
            vendor_count = len(neg)
        elif isinstance(state.get("vendor_offers"), dict):
            offers = state["vendor_offers"].get("offers")
            if isinstance(offers, list):
                vendor_count = len(offers)

        created_raw = request.get("created_at") or request.get("createdAt")
        started_at = datetime.now(timezone.utc)
        if created_raw:
            try:
                started_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            except ValueError:
                pass

        row = workflow_row_from_state(workflow_id, state, product_name=product.get("name"))
        entry = WorkflowIndexEntry(
            id=workflow_id,
            workflowId=workflow_id,
            requestId=str(request.get("request_id") or request.get("requestId") or workflow_id),
            organizationId=str(request.get("organization_id") or request.get("organizationId") or ""),
            productId=str(request.get("product_id") or request.get("productId") or ""),
            productName=row.product,
            requesterId=row.requested_by,
            prStatus=pr_status.value,
            startedAt=started_at,
            updatedAt=datetime.now(timezone.utc),
            vendorCount=vendor_count,
            needsAction=needs_action(pr_status),
        )
        await self._index_repo.upsert(entry)


def _index_phase(pr_status: str) -> str:
    from api.services.status_mapping import pr_status_to_phase_label

    return pr_status_to_phase_label(parse_pr_status(pr_status))


def _index_action_label(pr_status: str) -> str | None:
    from api.services.status_mapping import action_label

    return action_label(parse_pr_status(pr_status))


async def _assemble_workflow_detail(
    workflow_id: str,
    state: dict,
    *,
    vendor_repo: VendorRepository,
    events_repo: WorkflowEventsRepository,
) -> WorkflowDetailDTO:
    """Build a WorkflowDetailDTO from already-loaded session state.

    Shared by the REST handler and the WS factory so the two stay in sync.
    """
    vendor_ids: list[str] = []
    neg = state.get(NEGOTIATION_CONFIG_KEY)
    if isinstance(neg, dict):
        for vid, cfg in neg.items():
            if isinstance(cfg, dict):
                vendor_ids.append(str(cfg.get("vendor_id") or vid))
    offers_blob = state.get(VENDOR_OFFERS_KEY)
    if isinstance(offers_blob, dict):
        offers = offers_blob.get("offers")
        if isinstance(offers, list):
            for offer in offers:
                if isinstance(offer, dict):
                    vid = str(offer.get("vendorId") or offer.get("vendor_id") or "")
                    if vid:
                        vendor_ids.append(vid)
    vendor_ids = list(dict.fromkeys(vendor_ids))
    vendor_names = await vendor_repo.get_many(vendor_ids)
    events = await events_repo.list_for_workflow(workflow_id)
    return workflow_detail_from_state(
        workflow_id,
        state,
        vendor_names=vendor_names,
        events=events,
    )


async def build_workflow_detail_from_state(
    workflow_id: str,
    state: dict,
) -> WorkflowDetailDTO | None:
    """Build a WorkflowDetailDTO from a caller-supplied state snapshot.

    Used by mid-tool broadcasts: writes to ``tool_context.state`` are not
    visible to a separate ``VertexAiSessionService`` read until ADK persists
    the state delta at end-of-turn. Reading the session mid-tool would
    produce a stale DTO that dedupe drops as a duplicate hash. Passing the
    in-memory state directly bypasses that race.
    """
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None:
        logger.debug(
            "workflow_query.build_workflow_detail_from_state.no_ws_context workflow_id=%s",
            workflow_id,
        )
        return None

    try:
        return await _assemble_workflow_detail(
            workflow_id,
            state,
            vendor_repo=ctx.vendor_repo,
            events_repo=ctx.events_repo,
        )
    except Exception:
        logger.exception(
            "workflow_query.build_workflow_detail_from_state.assemble_failed workflow_id=%s",
            workflow_id,
        )
        return None


async def build_workflow_detail(workflow_id: str) -> WorkflowDetailDTO | None:
    """Module-level factory for WS state-changed broadcasts.

    Reads the WS context registry, fetches the buyer session, and assembles
    the same DTO the REST handler returns. Returns ``None`` if the WS
    context hasn't been initialized or the session is missing — the
    connection manager treats ``None`` as "skip this broadcast".
    """
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None:
        logger.debug(
            "workflow_query.build_workflow_detail.no_ws_context workflow_id=%s",
            workflow_id,
        )
        return None

    try:
        session = await ctx.buyer_reader.get_session(workflow_id)
    except Exception:
        logger.exception(
            "workflow_query.build_workflow_detail.session_read_failed workflow_id=%s",
            workflow_id,
        )
        return None

    if session is None:
        logger.debug(
            "workflow_query.build_workflow_detail.session_missing workflow_id=%s",
            workflow_id,
        )
        return None

    state = session.state if isinstance(session.state, dict) else {}
    try:
        return await _assemble_workflow_detail(
            workflow_id,
            state,
            vendor_repo=ctx.vendor_repo,
            events_repo=ctx.events_repo,
        )
    except Exception:
        logger.exception(
            "workflow_query.build_workflow_detail.assemble_failed workflow_id=%s",
            workflow_id,
        )
        return None
