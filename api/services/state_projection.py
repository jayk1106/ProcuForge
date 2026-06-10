"""Mirror ADK session state into Firestore.

Two helpers project the live buyer and vendor session-state dicts into
``workflow_state`` and ``vendor_thread_state`` Firestore documents. Both
write the full latest state under a nested ``state`` field plus a handful of
top-level indexed fields so list-page queries stay cheap. Writes are
idempotent (``merge=True``) and ``stateVersion`` is auto-incremented inside
the repo, so out-of-order broadcasts never roll the counter backwards.

The helpers are fire-and-forget from the perspective of the WebSocket
broadcast path: failures are logged and swallowed so a transient Firestore
hiccup cannot crash the runner loop or stall a subscriber update.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from api.services.status_mapping import parse_pr_status
from api.services.ui_mappers import workflow_row_from_state
from db.collections.vendor_thread_state import VendorThreadStateDoc
from db.collections.workflow_state import WorkflowStateDoc
from procu_forge_buyer.state_keys import (
    PR_STATUS_KEY,
    REQUEST_KEY,
    VENDOR_THREAD_OVERRIDES_KEY,
)
from procu_forge_vendor.state_keys import (
    COMMUNICATION_KEY,
    LAST_SELLING_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    PRODUCT_KEY as VENDOR_PRODUCT_KEY,
    ROUND_KEY,
    STATUS_KEY as VENDOR_STATUS_KEY,
)

logger = logging.getLogger(__name__)


@dataclass
class ProjectionPayload:
    """Carries the data the WS hook needs to mirror state into Firestore.

    Factories that should also persist state return ``(DTO, ProjectionPayload)``
    from their broadcast call. The connection manager dispatches the payload
    to :func:`_dispatch_projection` on the bound event loop, fire-and-forget.
    """

    kind: Literal["workflow", "vendor_thread"]
    state: dict[str, Any]
    workflow_id: str
    rfq_id: str | None = None
    vendor_id: str | None = None
    organization_id: str | None = None
    vendor_name: str = ""
    vendor_country: str = ""
    buyer_state: dict[str, Any] | None = None
    state_version: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def _dispatch_projection(payload: ProjectionPayload) -> None:
    """Route a ProjectionPayload to the right helper. Never raises."""
    try:
        if payload.kind == "workflow":
            await project_workflow_state(
                payload.workflow_id,
                payload.state,
                state_version=payload.state_version,
            )
        elif payload.kind == "vendor_thread":
            if not payload.rfq_id or not payload.vendor_id:
                logger.warning(
                    "state_projection.vendor_thread.missing_ids workflow_id=%s rfq_id=%s vendor_id=%s",
                    payload.workflow_id,
                    payload.rfq_id,
                    payload.vendor_id,
                )
                return
            await project_vendor_thread_state(
                payload.rfq_id,
                payload.state if payload.state else None,
                workflow_id=payload.workflow_id,
                vendor_id=payload.vendor_id,
                organization_id=payload.organization_id,
                vendor_name=payload.vendor_name,
                vendor_country=payload.vendor_country,
                buyer_state=payload.buyer_state,
                state_version=payload.state_version,
            )
    except Exception:  # noqa: BLE001 — projection is best-effort
        logger.exception(
            "state_projection.dispatch_failed kind=%s workflow_id=%s rfq_id=%s",
            payload.kind,
            payload.workflow_id,
            payload.rfq_id,
        )


async def project_workflow_state(
    workflow_id: str,
    buyer_state: dict[str, Any],
    *,
    state_version: int | None = None,
) -> None:
    """Upsert ``workflow_state/{workflow_id}`` from a buyer session state dict."""
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None or ctx.workflow_state_repo is None:
        logger.debug(
            "state_projection.workflow.no_ws_context workflow_id=%s",
            workflow_id,
        )
        return

    try:
        request = (
            buyer_state.get(REQUEST_KEY)
            if isinstance(buyer_state.get(REQUEST_KEY), dict)
            else {}
        )
        product = (
            buyer_state.get("product")
            if isinstance(buyer_state.get("product"), dict)
            else {}
        )

        organization_id = str(
            request.get("organization_id")
            or request.get("organizationId")
            or ctx.settings.workflow_default_organization_id
            or ""
        )
        if not organization_id:
            logger.warning(
                "state_projection.workflow.missing_org_id workflow_id=%s",
                workflow_id,
            )
            return

        row = workflow_row_from_state(
            workflow_id,
            buyer_state,
            product_name=product.get("name"),
        )

        started_at = _parse_iso(request.get("created_at") or request.get("createdAt"))
        if started_at is None:
            started_at = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        pr_status = parse_pr_status(buyer_state.get(PR_STATUS_KEY))

        doc = WorkflowStateDoc(
            id=workflow_id,
            workflowId=workflow_id,
            requestId=row.request_id,
            organizationId=organization_id,
            productId=str(
                request.get("product_id") or request.get("productId") or ""
            ),
            productName=row.product,
            requesterId=row.requested_by,
            prStatus=pr_status.value,
            startedAt=started_at,
            updatedAt=now,
            vendorCount=row.vendors,
            needsAction=row.needs_action,
            stateVersion=state_version or 0,
            state=buyer_state,
        )
        await ctx.workflow_state_repo.upsert(doc)
        logger.debug(
            "state_projection.workflow.upserted workflow_id=%s pr_status=%s vendors=%d",
            workflow_id,
            pr_status.value,
            row.vendors,
        )
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception(
            "state_projection.workflow.failed workflow_id=%s",
            workflow_id,
        )


async def project_vendor_thread_state(
    rfq_id: str,
    vendor_state: dict[str, Any] | None,
    *,
    workflow_id: str,
    vendor_id: str,
    organization_id: str | None = None,
    vendor_name: str = "",
    vendor_country: str = "",
    buyer_state: dict[str, Any] | None = None,
    state_version: int | None = None,
) -> None:
    """Upsert ``vendor_thread_state/{rfq_id}``.

    ``vendor_state`` may be ``None`` when the buyer initiates a thread before
    the vendor session has been created; the doc is still written with a
    stub state so the list row exists immediately.
    """
    from api.ws.context import get_ws_context

    ctx = get_ws_context()
    if ctx is None or ctx.vendor_thread_state_repo is None:
        logger.debug(
            "state_projection.vendor_thread.no_ws_context rfq_id=%s",
            rfq_id,
        )
        return

    try:
        override = _override_for(buyer_state, rfq_id)
        vstate = dict(vendor_state) if isinstance(vendor_state, dict) else None

        if vstate is None:
            state_blob: dict[str, Any] = {
                "initiating": True,
                "rfq_id": rfq_id,
                "vendor_id": vendor_id,
            }
        else:
            state_blob = vstate
        if override is not None:
            state_blob = dict(state_blob)
            state_blob["buyerOverride"] = override

        vendor_session_status = (
            str(vstate.get(VENDOR_STATUS_KEY) or "") if vstate else "INITIATING"
        )
        status = (
            str(override.get("status"))
            if isinstance(override, dict) and override.get("status")
            else vendor_session_status
        )

        product = (
            vstate.get(VENDOR_PRODUCT_KEY)
            if vstate and isinstance(vstate.get(VENDOR_PRODUCT_KEY), dict)
            else {}
        )
        currency = str(product.get("currency") or "USD")
        last_offer = vstate.get(LATEST_OFFER_PRICE_KEY) if vstate else None
        if last_offer is None and vstate:
            last_offer = vstate.get(LAST_SELLING_PRICE_KEY)
        round_val = vstate.get(ROUND_KEY) if vstate else 0

        comms = vstate.get(COMMUNICATION_KEY) if vstate else None
        message_count = len(comms) if isinstance(comms, list) else 0

        org_id = organization_id
        if not org_id:
            org_id = _org_from_buyer_state(buyer_state) or (
                ctx.settings.workflow_default_organization_id or ""
            )
        if not org_id:
            logger.warning(
                "state_projection.vendor_thread.missing_org_id rfq_id=%s",
                rfq_id,
            )
            return

        request_id = _request_id_from_buyer_state(buyer_state) or workflow_id

        now = datetime.now(timezone.utc)
        needs_attention = bool(
            isinstance(override, dict) and override.get("status") == "ESCALATED"
        )
        done_terminal = {
            "ACCEPTED",
            "VENDOR_WALKED_AWAY",
            "BUYER_WALKED_AWAY",
            "RFQ_CLOSED",
            "COMPLETE",
        }
        done = status in done_terminal or (
            isinstance(override, dict) and override.get("status") == "WALKED_AWAY"
        )

        doc = VendorThreadStateDoc(
            id=rfq_id,
            rfqId=rfq_id,
            workflowId=workflow_id,
            requestId=request_id,
            vendorId=vendor_id,
            vendorName=vendor_name or "",
            vendorCountry=vendor_country or "",
            organizationId=org_id,
            status=status,
            needsAction=needs_attention,
            lastOfferPrice=_coerce_float(last_offer),
            lastOfferCurrency=currency,
            round=int(round_val) if isinstance(round_val, (int, float)) else 0,
            messageCount=message_count,
            done=done,
            createdAt=now,
            updatedAt=now,
            stateVersion=state_version or 0,
            state=state_blob,
        )
        await ctx.vendor_thread_state_repo.upsert(doc)
        logger.debug(
            "state_projection.vendor_thread.upserted rfq_id=%s vendor_id=%s status=%s",
            rfq_id,
            vendor_id,
            status,
        )
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception(
            "state_projection.vendor_thread.failed rfq_id=%s vendor_id=%s",
            rfq_id,
            vendor_id,
        )


def _override_for(
    buyer_state: dict[str, Any] | None,
    rfq_id: str,
) -> dict[str, Any] | None:
    if not isinstance(buyer_state, dict):
        return None
    overrides = buyer_state.get(VENDOR_THREAD_OVERRIDES_KEY)
    if not isinstance(overrides, dict):
        return None
    entry = overrides.get(rfq_id)
    return entry if isinstance(entry, dict) else None


def _org_from_buyer_state(buyer_state: dict[str, Any] | None) -> str | None:
    if not isinstance(buyer_state, dict):
        return None
    request = buyer_state.get(REQUEST_KEY)
    if not isinstance(request, dict):
        return None
    raw = request.get("organization_id") or request.get("organizationId")
    return str(raw) if raw else None


def _request_id_from_buyer_state(buyer_state: dict[str, Any] | None) -> str | None:
    if not isinstance(buyer_state, dict):
        return None
    request = buyer_state.get(REQUEST_KEY)
    if not isinstance(request, dict):
        return None
    raw = request.get("request_id") or request.get("requestId")
    return str(raw) if raw else None


def _parse_iso(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ProjectionPayload",
    "_dispatch_projection",
    "project_workflow_state",
    "project_vendor_thread_state",
]
