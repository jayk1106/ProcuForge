"""Pre-resolve the escalation email recipient + render subject/body into state.

Runs as a ``before_agent_callback`` on ``pr_router`` so the LLM does not have to
call Firestore mid-stream. Idempotent: short-circuits when the email has already
been sent (``ESCALATION_EMAIL_SENT_AT_KEY`` set) by clearing the pending flag.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from google.adk.agents.callback_context import CallbackContext

from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_EMAIL_BODY_KEY,
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_EMAIL_SUBJECT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    ESCALATION_RECIPIENT_EMAIL_KEY,
    PR_STATUS_KEY,
    PRODUCT_KEY,
    REQUEST_KEY,
)

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "email_template.txt"


def _load_template() -> str:
    try:
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "Procurement Escalation — {workflow_id}\n\n"
            "Reason: {reason}\nSource: {source}\n\n"
            "Open workflow: {deep_link}\n"
        )


def _admin_fallback_email() -> str:
    return (os.environ.get("ADMIN_USER_EMAIL") or "").strip()


def _notify_fallback_email() -> str:
    return (os.environ.get("ESCALATION_NOTIFY_EMAIL") or "").strip()


def _web_base_url() -> str:
    return (os.environ.get("ESCALATION_WEB_BASE_URL") or "http://localhost:3000").rstrip("/")


async def _lookup_requester_email(requester_id: str) -> str:
    """Resolve the requester's email via UserRepository. Returns '' on miss."""
    if not requester_id:
        return ""
    try:
        from db.firestore.client import get_firestore_client
        from db.firestore.repositories.users import UserRepository

        repo = UserRepository(get_firestore_client())
        user = await repo.get(requester_id)
    except Exception:
        logger.exception(
            "escalation.recipient.lookup_failed requester_id=%s", requester_id
        )
        return ""
    if user is None:
        return ""
    return (user.email or "").strip()


async def _resolve_recipient(state: dict[str, Any]) -> str:
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    requester_id = str(
        request.get("requester_id") or request.get("requesterId") or ""
    ).strip()

    requester_email = await _lookup_requester_email(requester_id)
    if requester_email:
        return requester_email

    admin = _admin_fallback_email()
    if admin:
        return admin
    return _notify_fallback_email()


def _render_subject_and_body(
    workflow_id: str,
    state: dict[str, Any],
    context: dict[str, Any],
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

    deep_link = f"{_web_base_url()}/flows/{workflow_id}"

    template = _load_template()
    body = template.format(
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
    return subject, body


async def resolve_escalation_recipient(
    callback_context: CallbackContext,
) -> None:
    """Populate recipient/subject/body in state when an escalation email is pending."""
    state = callback_context.state
    if not state.get(ESCALATION_PENDING_NOTIFY_KEY):
        return None

    if state.get(ESCALATION_EMAIL_SENT_AT_KEY):
        state[ESCALATION_PENDING_NOTIFY_KEY] = False
        logger.info("escalation.recipient.skip reason=already_sent")
        return None

    context = state.get(ESCALATION_CONTEXT_KEY)
    if not isinstance(context, dict):
        logger.warning("escalation.recipient.skip reason=no_context")
        return None

    workflow_id = callback_context.session.id
    snapshot = callback_context.state.to_dict()

    recipient = await _resolve_recipient(snapshot)
    if not recipient:
        logger.warning(
            "escalation.recipient.unresolved workflow_id=%s", workflow_id
        )
        return None

    subject, body = _render_subject_and_body(workflow_id, snapshot, context)
    state[ESCALATION_RECIPIENT_EMAIL_KEY] = recipient
    state[ESCALATION_EMAIL_SUBJECT_KEY] = subject
    state[ESCALATION_EMAIL_BODY_KEY] = body
    logger.info(
        "escalation.recipient.resolved workflow_id=%s to=%s source=%s",
        workflow_id,
        recipient,
        context.get("source"),
    )
    return None


__all__ = ["resolve_escalation_recipient"]
