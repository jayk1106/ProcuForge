"""Tests for escalation email notification orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.config import APISettings
from api.services.escalation_notifications import notify_if_pending, resolve_recipient_email
from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    REQUEST_KEY,
)


@pytest.mark.asyncio
async def test_resolve_recipient_email_from_user_repo():
    settings = APISettings(
        admin_user_email="admin@example.com",
        escalation_notify_email="fallback@example.com",
    )
    user = MagicMock()
    user.email = "requester@example.com"
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=user)

    email = await resolve_recipient_email(
        {REQUEST_KEY: {"requester_id": "user-1"}},
        settings=settings,
        user_repo=repo,
    )
    assert email == "requester@example.com"


@pytest.mark.asyncio
async def test_resolve_recipient_email_falls_back_to_admin():
    settings = APISettings.model_construct(
        admin_user_email="admin@example.com",
        escalation_notify_email="fallback@example.com",
    )
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)

    email = await resolve_recipient_email(
        {REQUEST_KEY: {"requester_id": "missing"}},
        settings=settings,
        user_repo=repo,
    )
    assert email == "admin@example.com"


@pytest.mark.asyncio
async def test_notify_if_pending_skips_when_already_sent():
    settings = APISettings(
        mailgun_mcp_enabled=True,
        vertex_project_id="proj",
        reasoning_engine_app_name="engines/1",
        workflow_default_user_id="user-1",
    )
    session = MagicMock()
    session.state = {
        ESCALATION_PENDING_NOTIFY_KEY: True,
        ESCALATION_EMAIL_SENT_AT_KEY: "2026-01-01T00:00:00Z",
        ESCALATION_CONTEXT_KEY: {"source": "test", "reason": "r"},
    }
    session_service = AsyncMock()
    session_service.get_session = AsyncMock(return_value=session)

    with patch(
        "api.services.escalation_notifications.VertexAiSessionService",
        return_value=session_service,
    ), patch("api.services.escalation_notifications.send_email") as send_mock:
        await notify_if_pending("wf-1", settings=settings, user_repo=AsyncMock())
        send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notify_if_pending_sends_once():
    settings = APISettings.model_construct(
        mailgun_mcp_enabled=True,
        mailgun_api_key="key",
        mailgun_domain="example.com",
        mailgun_from_email="noreply@example.com",
        vertex_project_id="proj",
        reasoning_engine_app_name="engines/1",
        workflow_default_user_id="user-1",
        admin_user_email="admin@example.com",
        escalation_web_base_url="https://app.example.com",
    )
    session = MagicMock()
    session.state = {
        ESCALATION_PENDING_NOTIFY_KEY: True,
        ESCALATION_CONTEXT_KEY: {
            "source": "purchase_stall",
            "reason": "Stalled",
            "tier": "full",
            "trigger_status": "NEGOTIATION_COMPLETED",
            "phase": "neg",
            "recommended_action": "Review",
        },
        REQUEST_KEY: {"request_id": "PR-1", "requester_id": "user-1", "quantity": 1},
        "product": {"name": "Widget"},
    }
    session_service = AsyncMock()
    session_service.get_session = AsyncMock(return_value=session)
    session_service.append_event = AsyncMock()

    with patch(
        "api.services.escalation_notifications.VertexAiSessionService",
        return_value=session_service,
    ), patch(
        "api.services.escalation_notifications.send_email",
        return_value=True,
    ) as send_mock, patch(
        "api.ws.record_event",
    ), patch(
        "api.ws.broadcast_state",
    ):
        await notify_if_pending("wf-1", settings=settings, user_repo=AsyncMock())
        send_mock.assert_called_once()
        session_service.append_event.assert_called_once()
