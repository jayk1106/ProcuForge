"""List and detail queries for buyer workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.ui_dto import PagedWorkflowRows, WorkflowDetailDTO, WorkflowRowDTO
from api.services.session_reader import BuyerSessionReader
from api.services.status_mapping import (
    action_label,
    parse_pr_status,
    pr_status_human_label,
    pr_status_to_phase_label,
)
from api.services.ui_mappers import workflow_detail_from_state
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from db.firestore.repositories.workflow_state import WorkflowStateRepository
from procu_forge_buyer.state_keys import (
    NEGOTIATION_CONFIG_KEY,
    VENDOR_OFFERS_KEY,
)

logger = logging.getLogger(__name__)


_STATUS_FILTER_MAP: dict[str, str] = {
    "all": "",
    "progress": "IN_PROGRESS",
    "action": "NEEDS_ACTION",
    "completed": "DONE",
    "walked": "WALKED",
}


def _map_status_filter(value: str | None) -> str | None:
    """Translate the public API status param into the repo-level filter token."""
    if not value or value == "all":
        return None
    mapped = _STATUS_FILTER_MAP.get(value)
    return mapped or None


class WorkflowQueryService:
    def __init__(
        self,
        settings: APISettings,
        state_repo: WorkflowStateRepository,
        vendor_repo: VendorRepository,
        events_repo: WorkflowEventsRepository,
    ) -> None:
        self._settings = settings
        self._state_repo = state_repo
        self._vendor_repo = vendor_repo
        self._events_repo = events_repo
        self._buyer_reader = BuyerSessionReader(settings)

    def _ensure_configured(self) -> None:
        if not self._settings.vertex_project_id or not self._settings.reasoning_engine_app_name:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Buyer workflow runtime is not configured.",
            )

    async def list_workflows(
        self,
        organization_id: str | None = None,
        *,
        limit: int = 25,
        cursor: str | None = None,
        status_filter: str | None = None,
    ) -> PagedWorkflowRows:
        self._ensure_configured()
        org = organization_id or self._settings.workflow_default_organization_id
        if not org:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required.",
            )

        repo_filter = _map_status_filter(status_filter)
        docs, next_cursor = await self._state_repo.list_by_org(
            org, limit=limit, cursor=cursor, status_filter=repo_filter,
        )
        now = datetime.now(timezone.utc)
        items = [
            WorkflowRowDTO(
                id=d.workflow_id,
                requestId=d.request_id,
                product=d.product_name,
                requestedBy=d.requester_id,
                requestedAt=d.started_at.date().isoformat(),
                phase=pr_status_to_phase_label(parse_pr_status(d.pr_status)),  # type: ignore[arg-type]
                currentState=pr_status_human_label(parse_pr_status(d.pr_status)),
                vendors=d.vendor_count,
                days=max(
                    0,
                    (
                        now
                        - (
                            d.started_at.replace(tzinfo=timezone.utc)
                            if d.started_at.tzinfo is None
                            else d.started_at
                        )
                    ).days,
                ),
                needsAction=d.needs_action,
                actionLabel=action_label(parse_pr_status(d.pr_status)) if d.needs_action else None,
                walked=d.pr_status in {"NO_VENDOR_AVAILABLE", "NO_VENDORS_DISCOVERED"},
            )
            for d in docs
        ]
        return PagedWorkflowRows(items=items, nextCursor=next_cursor)

    async def get_workflow(self, workflow_id: str) -> WorkflowDetailDTO:
        self._ensure_configured()
        doc = await self._state_repo.get(workflow_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )
        return await _assemble_workflow_detail(
            workflow_id,
            doc.state,
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
) -> tuple[WorkflowDetailDTO, "ProjectionPayload"] | None:
    """Build a WorkflowDetailDTO from a caller-supplied state snapshot.

    Used by mid-tool broadcasts: writes to ``tool_context.state`` are not
    visible to a separate ``VertexAiSessionService`` read until ADK persists
    the state delta at end-of-turn. Reading the session mid-tool would
    produce a stale DTO that dedupe drops as a duplicate hash. Passing the
    in-memory state directly bypasses that race.

    Returns ``(dto, projection_payload)`` so the WS hook mirrors the state
    to Firestore alongside the broadcast.
    """
    from api.services.state_projection import ProjectionPayload
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None:
        logger.debug(
            "workflow_query.build_workflow_detail_from_state.no_ws_context workflow_id=%s",
            workflow_id,
        )
        return None

    try:
        dto = await _assemble_workflow_detail(
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

    payload = ProjectionPayload(
        kind="workflow",
        state=state,
        workflow_id=workflow_id,
    )
    return dto, payload


async def build_workflow_detail(
    workflow_id: str,
) -> tuple[WorkflowDetailDTO, "ProjectionPayload"] | None:
    """Module-level factory for WS state-changed broadcasts.

    Reads the WS context registry, fetches the buyer session, and assembles
    the same DTO the REST handler returns. Returns ``(dto, payload)`` so the
    WS hook mirrors the session state into ``workflow_state/{id}`` alongside
    the broadcast. Returns ``None`` if the WS context hasn't been
    initialized or the session is missing — the connection manager treats
    ``None`` as "skip this broadcast".
    """
    from api.services.state_projection import ProjectionPayload
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
    events = getattr(session, "events", None)
    state_version = len(events) if isinstance(events, list) else None

    try:
        dto = await _assemble_workflow_detail(
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

    payload = ProjectionPayload(
        kind="workflow",
        state=state,
        workflow_id=workflow_id,
        state_version=state_version,
    )
    return dto, payload
