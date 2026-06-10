"""List and detail queries for vendor negotiation threads."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from api.services.state_projection import ProjectionPayload

from api.config import APISettings
from api.schemas.ui_dto import PagedVendorThreadRows, VendorConvoDTO, VendorThreadRowDTO
from api.schemas.vendor_thread_status import VendorThreadStatus
from api.services.session_reader import BuyerSessionReader, VendorSessionReader
from api.services.ui_mappers import vendor_convo_from_state
from api.ws import broadcast_state, record_event, vendor_thread_channel
from db.collections.vendor_thread_state import VendorThreadStateDoc
from db.firestore.repositories.products import ProductRepository
from db.firestore.repositories.rfq_index import RfqIndexRepository
from db.firestore.repositories.vendor_thread_state import VendorThreadStateRepository
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    VENDOR_THREAD_OVERRIDES_KEY,
)

logger_name = __name__
logger = logging.getLogger(__name__)


class VendorThreadQueryService:
    def __init__(
        self,
        settings: APISettings,
        thread_state_repo: VendorThreadStateRepository,
        vendor_repo: VendorRepository,
        rfq_index_repo: RfqIndexRepository,
        events_repo: WorkflowEventsRepository,
        product_repo: ProductRepository | None = None,
    ) -> None:
        self._settings = settings
        self._thread_state_repo = thread_state_repo
        self._vendor_repo = vendor_repo
        self._rfq_index_repo = rfq_index_repo
        self._events_repo = events_repo
        self._product_repo = product_repo
        self._buyer_reader = BuyerSessionReader(settings)
        self._vendor_reader = VendorSessionReader(settings)

    def _ensure_configured(self) -> None:
        missing = []
        if not self._settings.vertex_project_id:
            missing.append("VERTEX_PROJECT_ID")
        if not self._settings.reasoning_engine_app_name:
            missing.append("BUYER_REASONING_ENGINE")
        if not self._settings.vendor_reasoning_engine_app_name:
            missing.append("VENDOR_REASONING_ENGINE")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vendor thread runtime is not configured. Missing: {', '.join(missing)}",
            )

    async def list_threads(
        self,
        organization_id: str | None = None,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> PagedVendorThreadRows:
        self._ensure_configured()
        org = organization_id or self._settings.workflow_default_organization_id
        if not org:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required.",
            )

        docs, next_cursor = await self._thread_state_repo.list_by_org(
            org, limit=limit, cursor=cursor,
        )
        # Names fall back to a per-org vendor lookup only for docs that were
        # projected before ``vendorName`` was populated. Skipping when present
        # avoids an extra Firestore read on the hot path.
        missing_names = [d.vendor_id for d in docs if not d.vendor_name]
        name_lookup = (
            await self._vendor_repo.get_many(missing_names) if missing_names else {}
        )
        items = [_row_from_thread_doc(d, name_lookup) for d in docs]
        return PagedVendorThreadRows(items=items, nextCursor=next_cursor)

    async def get_thread(self, rfq_id: str) -> VendorConvoDTO:
        self._ensure_configured()

        doc = await self._thread_state_repo.get(rfq_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vendor thread '{rfq_id}' not found.",
            )

        state = doc.state if isinstance(doc.state, dict) else {}
        override = state.get("buyerOverride") if isinstance(state.get("buyerOverride"), dict) else None

        vendor_doc = await self._vendor_repo.get(doc.vendor_id)

        product_doc = None
        product = state.get("product") if isinstance(state.get("product"), dict) else {}
        product_id = str(product.get("id") or "") if isinstance(product, dict) else ""
        if product_id and self._product_repo is not None:
            try:
                product_doc = await self._product_repo.get(product_id)
            except Exception:  # noqa: BLE001 — soft-fail; UI falls back to SKU/id from state
                product_doc = None

        events = await self._events_repo.list_for_vendor_thread(doc.workflow_id, rfq_id)

        return vendor_convo_from_state(
            rfq_id,
            state,
            workflow_id=doc.workflow_id,
            vendor_doc=vendor_doc,
            product_doc=product_doc,
            events=events,
            override=override,
        )

    async def get_thread_state(self, rfq_id: str) -> dict:
        """Return raw vendor and buyer session state for debugging."""
        self._ensure_configured()

        workflow_id, vendor_id = await self._resolve_rfq(rfq_id)

        vendor_state: dict = {}
        if vendor_id:
            vsession = await self._vendor_reader.get_session(rfq_id, vendor_id)
            if vsession is not None:
                vendor_state = vsession.state if isinstance(vsession.state, dict) else {}

        buyer_state: dict = {}
        if workflow_id:
            bsession = await self._buyer_reader.get_session(workflow_id)
            if bsession is not None:
                buyer_state = bsession.state if isinstance(bsession.state, dict) else {}

        return {
            "vendor_session_state": vendor_state,
            "buyer_session_state": buyer_state,
            "resolved": {"workflow_id": workflow_id, "vendor_id": vendor_id, "rfq_id": rfq_id},
        }

    async def escalate(self, rfq_id: str, reason: str | None = None) -> dict:
        return await self._apply_override(
            rfq_id,
            status=VendorThreadStatus.ESCALATED,
            reason=reason,
            event_type="vendor_thread_escalated",
            api_author="api:escalate",
            broadcast_reason="override_escalate",
        )

    async def walk_away(self, rfq_id: str, reason: str | None = None) -> dict:
        return await self._apply_override(
            rfq_id,
            status=VendorThreadStatus.WALKED_AWAY,
            reason=reason,
            event_type="vendor_thread_walked_away",
            api_author="api:walk_away",
            broadcast_reason="override_walk_away",
        )

    async def _apply_override(
        self,
        rfq_id: str,
        *,
        status: VendorThreadStatus,
        reason: str | None,
        event_type: str,
        api_author: str,
        broadcast_reason: str,
    ) -> dict:
        self._ensure_configured()

        workflow_id, vendor_id = await self._resolve_rfq(rfq_id)
        if not workflow_id or not vendor_id:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor thread '{rfq_id}' not found.",
            )

        session = await self._buyer_reader.get_session(workflow_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Buyer session '{workflow_id}' not found.",
            )

        from google.adk.events.event import Event
        from google.adk.events.event_actions import EventActions
        from google.adk.sessions import VertexAiSessionService

        current_overrides = (
            session.state.get(VENDOR_THREAD_OVERRIDES_KEY)
            if isinstance(session.state, dict)
            else None
        )
        overrides = dict(current_overrides) if isinstance(current_overrides, dict) else {}
        applied_at = datetime.now(timezone.utc).isoformat()
        overrides[rfq_id] = {
            "status": status.value,
            "reason": reason or "",
            "ts": applied_at,
            "vendor_id": vendor_id,
        }

        state_delta: dict = {VENDOR_THREAD_OVERRIDES_KEY: overrides}
        if status == VendorThreadStatus.ESCALATED:
            state_delta[ESCALATION_CONTEXT_KEY] = {
                "tier": "notify_only",
                "source": "manual_vendor_thread",
                "reason": reason or "Vendor thread escalated for human review",
                "trigger_status": (
                    session.state.get("pr_status")
                    if isinstance(session.state, dict)
                    else None
                ),
                "phase": "neg",
                "vendor_id": vendor_id,
                "rfq_id": rfq_id,
                "triggered_at": applied_at,
                "recommended_action": "Review escalated vendor thread and decide next action.",
            }
            state_delta[ESCALATION_PENDING_NOTIFY_KEY] = True

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        await session_service.append_event(
            session,
            Event(
                author=api_author,
                actions=EventActions(state_delta=state_delta),
            ),
        )

        record_event(
            workflow_id,
            event_type,
            {
                "rfq_id": rfq_id,
                "vendor_id": vendor_id,
                "status": status.value,
                "reason": reason or "",
            },
            vendor_thread_id=rfq_id,
            author=api_author,
        )

        broadcast_state(
            workflow_id,
            lambda: _factory_buyer(workflow_id),
            reason=f"{broadcast_reason}_buyer",
            workflow_id=workflow_id,
        )
        broadcast_state(
            vendor_thread_channel(rfq_id),
            lambda: build_vendor_convo(rfq_id),
            reason=f"{broadcast_reason}_vendor",
            workflow_id=workflow_id,
            vendor_thread_id=rfq_id,
        )

        return {
            "rfq_id": rfq_id,
            "workflow_id": workflow_id,
            "vendor_id": vendor_id,
            "status": status.value,
            "applied_at": applied_at,
        }

    async def _resolve_rfq(self, rfq_id: str) -> tuple[str, str]:
        """Look up ``(workflow_id, vendor_id)`` for an ``rfq_id``.

        Single O(1) read against ``rfq_index``. Returns empty strings when
        the rfq is unknown; callers raise 404.
        """
        entry = await self._rfq_index_repo.get(rfq_id)
        if entry is None:
            return "", ""
        return entry.workflow_id, entry.vendor_id


def _override_for_rfq(buyer_state: dict, rfq_id: str) -> dict | None:
    overrides = buyer_state.get(VENDOR_THREAD_OVERRIDES_KEY)
    if not isinstance(overrides, dict):
        return None
    entry = overrides.get(rfq_id)
    return entry if isinstance(entry, dict) else None


def _row_from_thread_doc(
    doc: VendorThreadStateDoc,
    name_lookup: dict,
) -> VendorThreadRowDTO:
    """Map a stored vendor-thread state doc to the wire DTO the UI consumes.

    Names are resolved from ``name_lookup`` only for docs whose ``vendorName``
    was never populated (legacy or pre-rollout writes). ``status`` mirrors the
    raw vendor-session status (overrides already applied during projection) so
    the list pill matches the detail page's summary card.
    """
    from api.services.ui_mappers import _format_relative

    name = doc.vendor_name or (
        (lookup_entry := name_lookup.get(doc.vendor_id)) and lookup_entry.name
    ) or doc.vendor_id

    return VendorThreadRowDTO(
        id=doc.rfq_id,
        vendorId=doc.vendor_id,
        name=name,
        country=doc.vendor_country or "—",
        tier="Tier-2",
        pr=doc.request_id or doc.workflow_id,
        workflowId=doc.workflow_id,
        last=_format_relative(doc.updated_at.isoformat()),
        state=doc.status or "UNKNOWN",
        unread=0,
        msgs=doc.message_count,
        round=doc.round if doc.round else None,
        latestPrice=doc.last_offer_price,
        done=doc.done,
    )


@dataclass
class _AssembledVendorConvo:
    """Bundle DTO + raw state alongside for the WS projection hook."""

    dto: VendorConvoDTO
    vendor_state: dict
    buyer_state: dict | None
    vendor_name: str
    vendor_country: str


async def _assemble_vendor_convo(
    rfq_id: str,
    *,
    workflow_id: str,
    vendor_id: str,
    vendor_reader: VendorSessionReader,
    buyer_reader: BuyerSessionReader,
    vendor_repo: VendorRepository,
    product_repo: ProductRepository | None,
    events_repo: WorkflowEventsRepository,
) -> _AssembledVendorConvo | None:
    """Shared by the REST handler and the WS factory.

    Returns ``None`` if the vendor session is missing; the REST handler
    promotes ``None`` to a 404 while the WS path silently skips the
    broadcast.
    """
    session = await vendor_reader.get_session(rfq_id, vendor_id)
    if session is None:
        return None

    state = session.state if isinstance(session.state, dict) else {}
    vendor_doc = await vendor_repo.get(vendor_id)
    product_doc = None
    product = state.get("product") if isinstance(state.get("product"), dict) else {}
    product_id = str(product.get("id") or "") if isinstance(product, dict) else ""
    if product_id and product_repo is not None:
        try:
            product_doc = await product_repo.get(product_id)
        except Exception:  # noqa: BLE001 — soft-fail; UI falls back to SKU/id from state
            product_doc = None
    events = await events_repo.list_for_vendor_thread(workflow_id, rfq_id)

    override: dict | None = None
    buyer_state_blob: dict | None = None
    if workflow_id:
        try:
            buyer_session = await buyer_reader.get_session(workflow_id)
        except Exception:  # noqa: BLE001 — override is optional
            buyer_session = None
        if buyer_session is not None:
            buyer_state_blob = (
                buyer_session.state if isinstance(buyer_session.state, dict) else {}
            )
            override = _override_for_rfq(buyer_state_blob, rfq_id)

    dto = vendor_convo_from_state(
        rfq_id,
        state,
        workflow_id=workflow_id,
        vendor_doc=vendor_doc,
        product_doc=product_doc,
        events=events,
        override=override,
    )
    from api.services.ui_mappers import _vendor_country

    country = _vendor_country(vendor_doc) if vendor_doc else ""
    return _AssembledVendorConvo(
        dto=dto,
        vendor_state=state,
        buyer_state=buyer_state_blob,
        vendor_name=vendor_doc.name if vendor_doc else "",
        vendor_country="" if country == "—" else country,
    )


async def build_vendor_convo(
    rfq_id: str,
) -> tuple[VendorConvoDTO, "ProjectionPayload"] | None:
    """Module-level factory for ``state_changed`` broadcasts on vt: channels.

    Resolves rfq → workflow/vendor via the rfq_index and assembles the same
    DTO ``get_thread`` returns alongside a ``ProjectionPayload`` so the WS
    hook mirrors the thread state into ``vendor_thread_state/{rfq_id}``.
    Returns ``None`` if the WS context is unset, the rfq cannot be resolved,
    or the vendor session is missing.
    """
    from api.services.state_projection import ProjectionPayload
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None:
        logger.debug(
            "vendor_thread_query.build_vendor_convo.no_ws_context rfq_id=%s",
            rfq_id,
        )
        return None

    try:
        entry = await ctx.rfq_index_repo.get(rfq_id)
    except Exception:
        logger.exception(
            "vendor_thread_query.build_vendor_convo.rfq_lookup_failed rfq_id=%s",
            rfq_id,
        )
        return None
    if entry is None:
        logger.debug(
            "vendor_thread_query.build_vendor_convo.rfq_unresolved rfq_id=%s",
            rfq_id,
        )
        return None

    try:
        assembled = await _assemble_vendor_convo(
            rfq_id,
            workflow_id=entry.workflow_id,
            vendor_id=entry.vendor_id,
            vendor_reader=ctx.vendor_reader,
            buyer_reader=ctx.buyer_reader,
            vendor_repo=ctx.vendor_repo,
            product_repo=ctx.product_repo,
            events_repo=ctx.events_repo,
        )
    except Exception:
        logger.exception(
            "vendor_thread_query.build_vendor_convo.assemble_failed rfq_id=%s",
            rfq_id,
        )
        return None

    if assembled is None:
        return None

    payload = ProjectionPayload(
        kind="vendor_thread",
        state=assembled.vendor_state,
        workflow_id=entry.workflow_id,
        rfq_id=rfq_id,
        vendor_id=entry.vendor_id,
        organization_id=entry.organization_id,
        vendor_name=assembled.vendor_name,
        vendor_country=assembled.vendor_country,
        buyer_state=assembled.buyer_state,
    )
    return assembled.dto, payload


async def _factory_buyer(workflow_id: str):
    """Lazy import shim so vendor_thread_query doesn't depend on workflow_query at import time."""
    from api.services.workflow_query import build_workflow_detail

    return await build_workflow_detail(workflow_id)
