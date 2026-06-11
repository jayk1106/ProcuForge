"""Tests for the HITL gating callback on purchase_manager_agent."""

from __future__ import annotations

from unittest.mock import MagicMock

from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.state_keys import (
    APPROVAL_REQUIRED_KEY,
    APPROVED_STEPS_KEY,
    INVOICE_KEY,
    INVOICE_VENDOR_ACK_KEY,
    PENDING_APPROVAL_KEY,
    PO_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
    SELECTED_VENDOR_KEY,
)
from procu_forge_buyer.subagents.purchase_manager.callbacks import gate_for_approval
from procu_forge_buyer.subagents.purchase_manager.tools import (
    COMPLETION_STEP,
    GRN_STEP,
    PO_STEP,
    maybe_apply_approval_gate,
)


def _ctx(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "test-session"
    # actions is a SimpleNamespace-like object so writes to .escalate stick.
    ctx.actions = MagicMock()
    ctx.actions.escalate = False
    ctx.actions.skip_summarization = False
    return ctx


def _state_at_po_gate() -> dict:
    return {
        APPROVAL_REQUIRED_KEY: True,
        PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value,
        SELECTED_VENDOR_KEY: {"vendor": "vendor-A", "final_price": 100.0},
    }


def _state_at_grn_gate() -> dict:
    return {
        APPROVAL_REQUIRED_KEY: True,
        APPROVED_STEPS_KEY: ["po"],
        PR_STATUS_KEY: PrStatus.PO_ACKNOWLEDGED.value,
        PO_KEY: {"po_number": "PO-1", "total_amount": 100.0},
        PO_VENDOR_ACK_KEY: {"message_type": "PO_ACKNOWLEDGED"},
    }


def _state_at_completion_gate() -> dict:
    return {
        APPROVAL_REQUIRED_KEY: True,
        APPROVED_STEPS_KEY: ["po", "grn"],
        PR_STATUS_KEY: PrStatus.INVOICE_UNDER_VERIFICATION.value,
        PO_KEY: {"po_number": "PO-1"},
        PO_VENDOR_ACK_KEY: {"ok": True},
        INVOICE_KEY: {"invoice_number": "INV-1"},
        INVOICE_VENDOR_ACK_KEY: {"ok": True},
    }


def test_gate_noop_when_approval_not_required():
    state = _state_at_po_gate()
    state[APPROVAL_REQUIRED_KEY] = False
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is None
    assert state[PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value
    assert PENDING_APPROVAL_KEY not in state
    assert ctx.actions.escalate is False


def test_gate_parks_at_po_when_required_and_no_acks():
    state = _state_at_po_gate()
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is not None  # returns minimal Content
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_PO_APPROVAL.value
    assert state[PENDING_APPROVAL_KEY]["step"] == "po"
    assert "vendor-A" in state[PENDING_APPROVAL_KEY]["reason"]
    assert ctx.actions.escalate is True
    assert ctx.actions.skip_summarization is True


def test_gate_noop_when_po_already_approved():
    state = _state_at_po_gate()
    state[APPROVED_STEPS_KEY] = ["po"]
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is None
    assert state[PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value
    assert PENDING_APPROVAL_KEY not in state


def test_gate_parks_at_grn_after_po_ack():
    state = _state_at_grn_gate()
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is not None
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_GRN_APPROVAL.value
    assert state[PENDING_APPROVAL_KEY]["step"] == "grn"
    assert "PO-1" in state[PENDING_APPROVAL_KEY]["reason"]
    assert ctx.actions.escalate is True


def test_gate_parks_at_completion_after_invoice_ack():
    state = _state_at_completion_gate()
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is not None
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_COMPLETION_APPROVAL.value
    assert state[PENDING_APPROVAL_KEY]["step"] == "completion"
    assert "INV-1" in state[PENDING_APPROVAL_KEY]["reason"]
    assert ctx.actions.escalate is True


def test_gate_noop_when_all_steps_done():
    state = _state_at_completion_gate()
    state[PROCESS_COMPLETE_VENDOR_ACK_KEY] = {"ok": True}
    ctx = _ctx(state)

    result = gate_for_approval(ctx)

    assert result is None
    assert PENDING_APPROVAL_KEY not in state


# ── Tool-level gate (the mid-chain case the before_agent_callback can't catch) ──


def test_tool_gate_returns_needs_approval_for_grn():
    # After PO has been approved and acknowledged, the agent chains directly to
    # send_grn_created in the same turn. The tool-level gate has to fire.
    state = _state_at_grn_gate()
    out = maybe_apply_approval_gate(state, step=GRN_STEP)

    assert out is not None
    assert out["ok"] is False
    assert out["error"] == "needs_approval"
    assert out["step"] == GRN_STEP
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_GRN_APPROVAL.value


def test_tool_gate_returns_needs_approval_for_completion():
    state = _state_at_completion_gate()
    out = maybe_apply_approval_gate(state, step=COMPLETION_STEP)

    assert out is not None
    assert out["ok"] is False
    assert out["step"] == COMPLETION_STEP
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_COMPLETION_APPROVAL.value


def test_tool_gate_noop_when_step_already_approved():
    state = _state_at_grn_gate()
    state[APPROVED_STEPS_KEY] = ["po", "grn"]
    out = maybe_apply_approval_gate(state, step=GRN_STEP)

    assert out is None
    assert state[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value
    assert PENDING_APPROVAL_KEY not in state


def test_tool_gate_noop_when_approval_off():
    state = _state_at_grn_gate()
    state[APPROVAL_REQUIRED_KEY] = False
    out = maybe_apply_approval_gate(state, step=GRN_STEP)

    assert out is None
    assert state[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value
