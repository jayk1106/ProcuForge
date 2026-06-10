"""Tests for resolve_escalation_recipient (before_agent_callback on pr_router)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_EMAIL_BODY_KEY,
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_EMAIL_SUBJECT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    ESCALATION_RECIPIENT_EMAIL_KEY,
    PRODUCT_KEY,
    REQUEST_KEY,
)
from procu_forge_buyer.subagents.escalation_notifier import recipient as recipient_mod
from procu_forge_buyer.subagents.escalation_notifier.recipient import (
    resolve_escalation_recipient,
)


class _State(dict):
    def to_dict(self) -> dict:
        return dict(self)


def _ctx(state: dict, *, session_id: str = "wf-1") -> SimpleNamespace:
    return SimpleNamespace(state=_State(state), session=SimpleNamespace(id=session_id))


def _pending_state() -> dict:
    return {
        ESCALATION_PENDING_NOTIFY_KEY: True,
        ESCALATION_CONTEXT_KEY: {
            "source": "purchase_stall",
            "reason": "Stalled",
            "tier": "full",
            "trigger_status": "NEGOTIATION_COMPLETED",
            "phase": "neg",
            "recommended_action": "Review",
        },
        REQUEST_KEY: {
            "request_id": "PR-1",
            "requester_id": "user-1",
            "quantity": 5,
        },
        PRODUCT_KEY: {"name": "Widget"},
    }


@pytest.mark.asyncio
async def test_noop_when_not_pending():
    ctx = _ctx({})
    await resolve_escalation_recipient(ctx)
    assert ESCALATION_RECIPIENT_EMAIL_KEY not in ctx.state


@pytest.mark.asyncio
async def test_clears_pending_when_already_sent(monkeypatch):
    state = _pending_state()
    state[ESCALATION_EMAIL_SENT_AT_KEY] = "2026-01-01T00:00:00Z"
    ctx = _ctx(state)
    await resolve_escalation_recipient(ctx)
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is False
    assert ESCALATION_RECIPIENT_EMAIL_KEY not in ctx.state


@pytest.mark.asyncio
async def test_resolves_from_requester(monkeypatch):
    ctx = _ctx(_pending_state())
    user = MagicMock(email="requester@example.com")
    monkeypatch.setattr(
        recipient_mod,
        "_lookup_requester_email",
        AsyncMock(return_value="requester@example.com"),
    )

    await resolve_escalation_recipient(ctx)
    assert ctx.state[ESCALATION_RECIPIENT_EMAIL_KEY] == "requester@example.com"
    assert ctx.state[ESCALATION_EMAIL_SUBJECT_KEY].startswith("[ProcuForge] Escalation")
    assert "PR-1" in ctx.state[ESCALATION_EMAIL_SUBJECT_KEY]
    body = ctx.state[ESCALATION_EMAIL_BODY_KEY]
    assert "Widget" in body and "Stalled" in body and "wf-1" in body
    del user


@pytest.mark.asyncio
async def test_falls_back_to_admin(monkeypatch):
    ctx = _ctx(_pending_state())
    monkeypatch.setattr(
        recipient_mod, "_lookup_requester_email", AsyncMock(return_value="")
    )
    monkeypatch.setattr(recipient_mod, "_admin_fallback_email", lambda: "admin@example.com")
    monkeypatch.setattr(recipient_mod, "_notify_fallback_email", lambda: "ops@example.com")

    await resolve_escalation_recipient(ctx)
    assert ctx.state[ESCALATION_RECIPIENT_EMAIL_KEY] == "admin@example.com"


@pytest.mark.asyncio
async def test_falls_back_to_notify_email(monkeypatch):
    ctx = _ctx(_pending_state())
    monkeypatch.setattr(
        recipient_mod, "_lookup_requester_email", AsyncMock(return_value="")
    )
    monkeypatch.setattr(recipient_mod, "_admin_fallback_email", lambda: "")
    monkeypatch.setattr(recipient_mod, "_notify_fallback_email", lambda: "ops@example.com")

    await resolve_escalation_recipient(ctx)
    assert ctx.state[ESCALATION_RECIPIENT_EMAIL_KEY] == "ops@example.com"


@pytest.mark.asyncio
async def test_unresolved_recipient_does_not_write_state(monkeypatch):
    ctx = _ctx(_pending_state())
    monkeypatch.setattr(
        recipient_mod, "_lookup_requester_email", AsyncMock(return_value="")
    )
    monkeypatch.setattr(recipient_mod, "_admin_fallback_email", lambda: "")
    monkeypatch.setattr(recipient_mod, "_notify_fallback_email", lambda: "")

    await resolve_escalation_recipient(ctx)
    assert ESCALATION_RECIPIENT_EMAIL_KEY not in ctx.state
    assert ESCALATION_EMAIL_SUBJECT_KEY not in ctx.state
