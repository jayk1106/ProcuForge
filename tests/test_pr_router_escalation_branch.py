"""Tests for stop_loop_if_terminal's escalation-pending branch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from procu_forge_buyer.callbacks import stop_loop_if_terminal
from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.state_keys import (
    ESCALATION_EMAIL_SENT_AT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    PR_STATUS_KEY,
)


def _ctx(state: dict) -> SimpleNamespace:
    actions = SimpleNamespace(escalate=False, skip_summarization=False)
    return SimpleNamespace(state=state, actions=actions)


def test_terminates_on_escalated_when_no_pending_notify():
    ctx = _ctx({PR_STATUS_KEY: PrStatus.ESCALATED.value})
    result = stop_loop_if_terminal(ctx)
    assert result is not None
    assert ctx.actions.escalate is True


def test_does_not_terminate_when_pending_notify_unsent():
    ctx = _ctx(
        {
            PR_STATUS_KEY: PrStatus.ESCALATED.value,
            ESCALATION_PENDING_NOTIFY_KEY: True,
        }
    )
    result = stop_loop_if_terminal(ctx)
    assert result is None
    assert ctx.actions.escalate is False


def test_terminates_when_pending_notify_already_sent():
    ctx = _ctx(
        {
            PR_STATUS_KEY: PrStatus.ESCALATED.value,
            ESCALATION_PENDING_NOTIFY_KEY: True,
            ESCALATION_EMAIL_SENT_AT_KEY: "2026-01-01T00:00:00Z",
        }
    )
    result = stop_loop_if_terminal(ctx)
    assert result is not None
    assert ctx.actions.escalate is True


def test_passes_through_non_terminal_status():
    ctx = _ctx({PR_STATUS_KEY: PrStatus.NEGOTIATION_IN_PROGRESS.value})
    assert stop_loop_if_terminal(ctx) is None
    assert ctx.actions.escalate is False
