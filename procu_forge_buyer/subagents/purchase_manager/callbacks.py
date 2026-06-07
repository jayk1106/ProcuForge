"""Callbacks for purchase_manager_agent: advance pr_status after validated A2A steps."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from ...callbacks import (
    _plan_summary,
    _product_id,
    _request_id,
    _session_state_dict,
    managed_log_after_handler,
    managed_log_before_handler,
)
from ...pr_status import PrStatus
from ...pr_status_transitions import (
    pr_status_line,
    sync_purchase_pr_status_from_acks,
    transition_to_awaiting_completion_approval,
    transition_to_awaiting_grn_approval,
    transition_to_awaiting_po_approval,
    transition_to_escalated,
)
from ...state_keys import (
    APPROVAL_REQUIRED_KEY,
    APPROVED_STEPS_KEY,
    INVOICE_KEY,
    INVOICE_VENDOR_ACK_KEY,
    NEGOTIATION_CONFIG_KEY,
    PENDING_APPROVAL_KEY,
    PLANNER_PLAN_KEY,
    PO_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
    PURCHASE_STALL_STREAK_KEY,
    PURCHASE_STEP_SNAPSHOT_KEY,
    SELECTED_VENDOR_KEY,
)
from .tools import _purchase_made_progress, purchase_progress_snapshot

logger = logging.getLogger(__name__)

_STALL_ESCALATE_THRESHOLD = 2

_PURCHASE_PHASE_STATUSES = frozenset(
    {
        PrStatus.VENDOR_SELECTED.value,
        PrStatus.PO_ISSUED.value,
        PrStatus.PO_ACKNOWLEDGED.value,
        PrStatus.INVOICE_UNDER_VERIFICATION.value,
        # HITL gates: parked turns must not count toward the stall streak.
        PrStatus.AWAITING_PO_APPROVAL.value,
        PrStatus.AWAITING_GRN_APPROVAL.value,
        PrStatus.AWAITING_COMPLETION_APPROVAL.value,
    }
)

# Map from "next step" → (gate transition, human-readable reason template).
# Step values match those stored in APPROVED_STEPS_KEY.
_PO_STEP = "po"
_GRN_STEP = "grn"
_COMPLETION_STEP = "completion"


def _resolve_next_step(state: Any) -> str | None:
    """Return the next purchase step that has not yet been vendor-confirmed.

    Mirrors the ordering used by ``build_purchase_progress`` in ``tools.py``.
    """
    if not state.get(PO_VENDOR_ACK_KEY):
        return _PO_STEP
    if not state.get(INVOICE_VENDOR_ACK_KEY):
        return _GRN_STEP
    if not state.get(PROCESS_COMPLETE_VENDOR_ACK_KEY):
        return _COMPLETION_STEP
    return None


def _selected_vendor_label(state: Any) -> str:
    selected = state.get(SELECTED_VENDOR_KEY)
    if isinstance(selected, dict):
        return str(selected.get("vendor") or "the selected vendor")
    return "the selected vendor"


def _reason_for_step(step: str, state: Any) -> str:
    if step == _PO_STEP:
        vendor = _selected_vendor_label(state)
        po = state.get(PO_KEY) if isinstance(state.get(PO_KEY), dict) else {}
        amount = po.get("total_amount") if isinstance(po, dict) else None
        if amount:
            return f"Approval required before sending PO to {vendor} (total {amount})."
        return f"Approval required before sending PO to {vendor}."
    if step == _GRN_STEP:
        po = state.get(PO_KEY) if isinstance(state.get(PO_KEY), dict) else {}
        po_number = po.get("po_number") if isinstance(po, dict) else None
        if po_number:
            return f"Approval required before sending GRN for PO {po_number}."
        return "Approval required before sending GRN to the vendor."
    if step == _COMPLETION_STEP:
        invoice = state.get(INVOICE_KEY) if isinstance(state.get(INVOICE_KEY), dict) else {}
        invoice_number = invoice.get("invoice_number") if isinstance(invoice, dict) else None
        if invoice_number:
            return (
                f"Approval required before closing the procurement for invoice {invoice_number}."
            )
        return "Approval required before closing the procurement."
    return "Approval required before continuing."


def _apply_gate_transition(state: Any, step: str) -> None:
    if step == _PO_STEP:
        transition_to_awaiting_po_approval(state)
    elif step == _GRN_STEP:
        transition_to_awaiting_grn_approval(state)
    elif step == _COMPLETION_STEP:
        transition_to_awaiting_completion_approval(state)


def _purchase_progress_line(st: dict[str, Any]) -> str:
    snap = purchase_progress_snapshot(st)
    acks = snap.get("acks") or {}
    closed = snap.get("rfq_closed_losers") or []
    return (
        "acks po=%s inv=%s pc=%s rfq_closed=%s"
        % (
            acks.get("po_vendor_ack"),
            acks.get("invoice_vendor_ack"),
            acks.get("process_complete_vendor_ack"),
            ",".join(closed) or "-",
        )
    )


def _purchase_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "purchase_manager_agent start session_id=%s request_id=%s product_id=%s plan=%s %s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
            _purchase_progress_line(st),
        )
    )


def _purchase_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "purchase_manager_agent end session_id=%s request_id=%s product_id=%s plan=%s %s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
            _purchase_progress_line(st),
        )
    )


log_purchase_manager_before_agent = partial(
    managed_log_before_handler, span="PURCHASE_MANAGER", detail_line=_purchase_before
)
log_purchase_manager_after_agent = partial(
    managed_log_after_handler,
    span="PURCHASE_MANAGER",
    detail_line=_purchase_after,
    trailing_lines=None,
)


def gate_for_approval(callback_context: CallbackContext) -> types.Content | None:
    """Park the purchase loop at the next step when human approval is required.

    No-op unless ``approval_required`` is set in session state. When the next
    purchase step has not yet been signed off (absent from ``approved_steps``)
    this writes ``pending_approval``, flips ``pr_status`` to the matching
    ``AWAITING_*_APPROVAL`` value, and escalates the enclosing ``LoopAgent`` so
    ``stop_loop_if_terminal`` exits the loop on the way out.
    """
    state = callback_context.state
    if not state.get(APPROVAL_REQUIRED_KEY):
        return None

    step = _resolve_next_step(state)
    if step is None:
        return None

    approved = state.get(APPROVED_STEPS_KEY) or []
    if isinstance(approved, list) and step in approved:
        return None

    reason = _reason_for_step(step, state)
    state[PENDING_APPROVAL_KEY] = {
        "step": step,
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _apply_gate_transition(state, step)

    callback_context.actions.escalate = True
    callback_context.actions.skip_summarization = True
    logger.info(
        "purchase_manager.gate session_id=%s step=%s pr_status=%s",
        callback_context.session.id,
        step,
        state.get(PR_STATUS_KEY),
    )
    return types.Content(role="model", parts=[types.Part(text=" ")])


def purchase_manager_before_agent(callback_context: CallbackContext) -> None:
    """Snapshot progress for stall detection and emit start span."""
    state = callback_context.state
    state[PURCHASE_STEP_SNAPSHOT_KEY] = purchase_progress_snapshot(state)
    log_purchase_manager_before_agent(callback_context)
    return None


def purchase_manager_after_agent(callback_context: CallbackContext) -> None:
    """Advance pr_status only after vendor-confirmed ack keys; detect stalls."""
    state = callback_context.state
    current = state.get(PR_STATUS_KEY)

    snapshot = state.get(PURCHASE_STEP_SNAPSHOT_KEY) or {}
    current_snap = purchase_progress_snapshot(state)
    progress = _purchase_made_progress(snapshot, current_snap)
    status_synced = sync_purchase_pr_status_from_acks(state)
    if status_synced:
        progress = True

    if progress:
        state[PURCHASE_STALL_STREAK_KEY] = 0
    elif current not in _PURCHASE_PHASE_STATUSES:
        streak = int(state.get(PURCHASE_STALL_STREAK_KEY) or 0) + 1
        state[PURCHASE_STALL_STREAK_KEY] = streak
        if streak >= _STALL_ESCALATE_THRESHOLD and current not in (
            PrStatus.ESCALATED.value,
            PrStatus.COMPLETED.value,
            PrStatus.CANCELLED.value,
        ):
            logger.warning(
                "purchase_manager_stall_escalate session_id=%s streak=%d pr_status=%s snap=%s",
                callback_context.session.id,
                streak,
                current,
                current_snap,
            )
            transition_to_escalated(state)
            log_purchase_manager_after_agent(callback_context)
            return None

    log_purchase_manager_after_agent(callback_context)
    return None


__all__ = [
    "gate_for_approval",
    "purchase_manager_after_agent",
    "purchase_manager_before_agent",
    "log_purchase_manager_after_agent",
    "log_purchase_manager_before_agent",
]
