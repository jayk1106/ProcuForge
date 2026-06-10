"""Stamp ESCALATION_EMAIL_SENT_AT_KEY when Mailgun's send_email tool returns success."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from procu_forge_buyer.state_keys import (
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
)

logger = logging.getLogger(__name__)


def _looks_successful(response: Any) -> bool:
    """Heuristic: Mailgun MCP send_email returns the API JSON with an ``id`` field."""
    if response is None:
        return False
    if isinstance(response, dict):
        text = response.get("message") or response.get("status")
        if response.get("id") or response.get("messageId"):
            return True
        if isinstance(text, str) and "queued" in text.lower():
            return True
        if response.get("isError") is True or response.get("error"):
            return False
        content = response.get("content")
        if isinstance(content, list) and content:
            joined = " ".join(
                str(item.get("text") or "") if isinstance(item, dict) else str(item)
                for item in content
            )
            lowered = joined.lower()
            if "queued" in lowered or '"id"' in lowered:
                return True
            if "error" in lowered or "fail" in lowered:
                return False
    return False


async def after_send_email_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any] | Any,
) -> dict[str, Any] | None:
    """Mark escalation as sent only on a successful Mailgun ``send_email`` call."""
    if tool.name != "send_email":
        return None
    if not _looks_successful(tool_response):
        logger.warning(
            "escalation.notify.send_email_unsuccessful response_preview=%s",
            str(tool_response)[:200],
        )
        return None

    sent_at = datetime.now(timezone.utc).isoformat()
    tool_context.state[ESCALATION_EMAIL_SENT_AT_KEY] = sent_at
    tool_context.state[ESCALATION_PENDING_NOTIFY_KEY] = False
    logger.info(
        "escalation.notify.sent to=%s subject=%s",
        args.get("to"),
        str(args.get("subject"))[:80],
    )
    return None


__all__ = ["after_send_email_callback"]
