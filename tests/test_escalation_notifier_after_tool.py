"""Tests for after_send_email_callback in escalation_notifier."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from procu_forge_buyer.state_keys import (
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
)
from procu_forge_buyer.subagents.escalation_notifier.callbacks import (
    after_send_email_callback,
)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.state = {ESCALATION_PENDING_NOTIFY_KEY: True}
    return ctx


def _tool(name: str = "send_email") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    return tool


@pytest.mark.asyncio
async def test_marks_sent_on_queued_response():
    ctx = _ctx()
    await after_send_email_callback(
        _tool(),
        {"to": "ops@x.com", "subject": "Escalation"},
        ctx,
        {"id": "<abc@mg>", "message": "Queued. Thank you."},
    )
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is False
    assert ctx.state[ESCALATION_EMAIL_SENT_AT_KEY]


@pytest.mark.asyncio
async def test_marks_sent_on_mcp_content_with_id():
    ctx = _ctx()
    await after_send_email_callback(
        _tool(),
        {"to": "ops@x.com", "subject": "Escalation"},
        ctx,
        {"content": [{"type": "text", "text": '{"id":"<abc@mg>","message":"Queued"}'}]},
    )
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is False
    assert ctx.state[ESCALATION_EMAIL_SENT_AT_KEY]


@pytest.mark.asyncio
async def test_does_not_mark_sent_on_error_response():
    ctx = _ctx()
    await after_send_email_callback(
        _tool(),
        {"to": "ops@x.com", "subject": "Escalation"},
        ctx,
        {"isError": True, "error": "401 Unauthorized"},
    )
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is True
    assert ESCALATION_EMAIL_SENT_AT_KEY not in ctx.state


@pytest.mark.asyncio
async def test_does_not_mark_sent_on_empty_response():
    ctx = _ctx()
    await after_send_email_callback(
        _tool(),
        {"to": "ops@x.com", "subject": "Escalation"},
        ctx,
        None,
    )
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is True
    assert ESCALATION_EMAIL_SENT_AT_KEY not in ctx.state


@pytest.mark.asyncio
async def test_ignored_for_non_send_email_tool():
    ctx = _ctx()
    await after_send_email_callback(
        _tool("get_logs"),
        {},
        ctx,
        {"id": "ignored"},
    )
    assert ctx.state[ESCALATION_PENDING_NOTIFY_KEY] is True
    assert ESCALATION_EMAIL_SENT_AT_KEY not in ctx.state
