"""One-way email delivery via Mailgun HTTP API.

Uses the Mailgun REST API directly (same capability as @mailgun/mcp-server
``send_email`` tool) so FastAPI background tasks do not spawn MCP subprocesses.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from api.config import APISettings, get_api_settings

logger = logging.getLogger(__name__)


def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    settings: APISettings | None = None,
) -> bool:
    """Send a transactional email. Returns True on success, False on failure."""
    cfg = settings or get_api_settings()
    if not cfg.mailgun_mcp_enabled:
        logger.info("mailgun.send skipped reason=disabled to=%s", to)
        return False
    if not cfg.mailgun_api_key or not cfg.mailgun_domain:
        logger.warning("mailgun.send skipped reason=missing_config to=%s", to)
        return False
    if not to.strip():
        logger.warning("mailgun.send skipped reason=empty_recipient")
        return False

    url = f"https://api.mailgun.net/v3/{cfg.mailgun_domain}/messages"
    data: dict[str, Any] = {
        "from": cfg.mailgun_from_email or f"escalations@{cfg.mailgun_domain}",
        "to": to.strip(),
        "subject": subject,
        "text": text,
    }
    if html:
        data["html"] = html

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                auth=("api", cfg.mailgun_api_key),
                data=data,
            )
        if response.status_code >= 400:
            logger.error(
                "mailgun.send.failed status=%s body=%s to=%s",
                response.status_code,
                response.text[:500],
                to,
            )
            return False
        logger.info("mailgun.send.ok to=%s subject=%s", to, subject[:80])
        return True
    except Exception:
        logger.exception("mailgun.send.error to=%s", to)
        return False
