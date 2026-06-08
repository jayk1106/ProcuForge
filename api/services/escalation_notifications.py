"""Fire-and-forget escalation email notifications (API layer)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import VertexAiSessionService

from api.config import APISettings, get_api_settings
from api.services.mailgun_mcp import send_email
from db.firestore.repositories.users import UserRepository
from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    PR_STATUS_KEY,
    PREVIOUS_PR_STATUS_KEY,
    PRODUCT_KEY,
    REQUEST_KEY,
)

logger = logging.getLogger(__name__)

_EMAIL_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "escalation_email.txt"


def _load_template() -> str:
    try:
        return _EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "Procurement Escalation — {workflow_id}\n\n"
            "Reason: {reason}\nSource: {source}\n\n"
            "Open workflow: {deep_link}\n"
        )


async def resolve_recipient_email(
    state: dict[str, Any],
    *,
    settings: APISettings,
    user_repo: UserRepository | None = None,
) -> str:
    """Resolve escalation recipient: requester → admin → fallback."""
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    requester_id = str(
        request.get("requester_id") or request.get("requesterId") or ""
    ).strip()

    if requester_id and user_repo is not None:
        try:
            user = await user_repo.get(requester_id)
            if user is not None and user.email.strip():
                return user.email.strip()
        except Exception:
            logger.exception(
                "escalation.recipient.lookup_failed requester_id=%s",
                requester_id,
            )

    if settings.admin_user_email.strip():
        return settings.admin_user_email.strip()
    return settings.escalation_notify_email.strip()


def _build_email_body(
    *,
    workflow_id: str,
    context: dict[str, Any],
    state: dict[str, Any],
    settings: APISettings,
) -> tuple[str, str]:
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    product = state.get(PRODUCT_KEY) if isinstance(state.get(PRODUCT_KEY), dict) else {}

    request_id = str(request.get("request_id") or request.get("requestId") or workflow_id)
    product_label = str(product.get("name") or request.get("product_id") or "Unknown")
    quantity = str(request.get("quantity") or "—")

    vendor_id = context.get("vendor_id")
    rfq_id = context.get("rfq_id")
    vendor_block = ""
    if vendor_id or rfq_id:
        vendor_block = f"Vendor: {vendor_id or '—'}\nRFQ: {rfq_id or '—'}"

    base_url = (settings.escalation_web_base_url or "http://localhost:3000").rstrip("/")
    deep_link = f"{base_url}/flows/{workflow_id}"

    template = _load_template()
    text = template.format(
        workflow_id=workflow_id,
        reason=context.get("reason") or "Human review required",
        source=context.get("source") or "unknown",
        tier=context.get("tier") or "notify_only",
        trigger_status=context.get("trigger_status") or state.get(PR_STATUS_KEY) or "—",
        phase=context.get("phase") or "—",
        request_id=request_id,
        product_label=product_label,
        quantity=quantity,
        vendor_block=vendor_block,
        recommended_action=context.get("recommended_action") or "Review the workflow.",
        deep_link=deep_link,
    )
    source = context.get("source") or "escalation"
    subject = f"[ProcuForge] Escalation: {source.replace('_', ' ')} — {request_id}"
    return subject, text


async def notify_if_pending(
    workflow_id: str,
    *,
    settings: APISettings | None = None,
    user_repo: UserRepository | None = None,
) -> None:
    """Send escalation email when session state has escalation_pending_notify set."""
    cfg = settings or get_api_settings()
    if not cfg.mailgun_mcp_enabled:
        return
    if not cfg.vertex_project_id or not cfg.reasoning_engine_app_name:
        logger.warning("escalation.notify skipped reason=vertex_not_configured")
        return

    user_id = cfg.workflow_default_user_id or ""
    if not user_id:
        logger.warning("escalation.notify skipped reason=no_default_user_id")
        return

    try:
        session_service = VertexAiSessionService(
            project=cfg.vertex_project_id,
            location=cfg.vertex_location,
        )
        session = await session_service.get_session(
            app_name=cfg.reasoning_engine_app_name,
            user_id=user_id,
            session_id=workflow_id,
        )
        if session is None:
            logger.warning("escalation.notify skipped workflow_id=%s reason=no_session", workflow_id)
            return

        state = session.state if isinstance(session.state, dict) else {}
        if not state.get(ESCALATION_PENDING_NOTIFY_KEY):
            return
        if state.get(ESCALATION_EMAIL_SENT_AT_KEY):
            logger.info("escalation.notify skipped workflow_id=%s reason=already_sent", workflow_id)
            return

        context = state.get(ESCALATION_CONTEXT_KEY)
        if not isinstance(context, dict):
            logger.warning("escalation.notify skipped workflow_id=%s reason=no_context", workflow_id)
            return

        recipient = await resolve_recipient_email(state, settings=cfg, user_repo=user_repo)
        if not recipient:
            logger.warning("escalation.notify skipped workflow_id=%s reason=no_recipient", workflow_id)
            return

        subject, body = _build_email_body(
            workflow_id=workflow_id,
            context=context,
            state=state,
            settings=cfg,
        )
        sent = send_email(to=recipient, subject=subject, text=body, settings=cfg)
        if not sent:
            return

        sent_at = datetime.now(timezone.utc).isoformat()
        await session_service.append_event(
            session,
            Event(
                invocation_id=f"escalation-notify-{uuid.uuid4().hex}",
                author="api:escalation",
                actions=EventActions(
                    state_delta={
                        ESCALATION_PENDING_NOTIFY_KEY: False,
                        ESCALATION_EMAIL_SENT_AT_KEY: sent_at,
                    }
                ),
            ),
        )

        from api.services.workflow_query import build_workflow_detail
        from api.ws import broadcast_state, record_event

        record_event(
            workflow_id,
            "workflow_escalated",
            {
                "source": context.get("source"),
                "reason": context.get("reason"),
                "tier": context.get("tier"),
                "recipient": recipient,
            },
            author="api:escalation",
        )
        broadcast_state(
            workflow_id,
            lambda: build_workflow_detail(workflow_id),
            reason="escalation_notified",
            workflow_id=workflow_id,
        )
        logger.info(
            "escalation.notify.sent workflow_id=%s to=%s source=%s",
            workflow_id,
            recipient,
            context.get("source"),
        )
    except Exception:
        logger.exception("escalation.notify.failed workflow_id=%s", workflow_id)


def schedule_notify_if_pending(workflow_id: str) -> None:
    """Run notify_if_pending from a sync background thread."""
    import asyncio

    from db.firestore.client import get_firestore_client
    from db.firestore.repositories.users import UserRepository

    async def _run() -> None:
        repo = UserRepository(get_firestore_client())
        await notify_if_pending(workflow_id, user_repo=repo)

    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("escalation.schedule.failed workflow_id=%s", workflow_id)
