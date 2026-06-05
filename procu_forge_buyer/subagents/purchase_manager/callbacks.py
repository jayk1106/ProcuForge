"""Callbacks for purchase_manager_agent: advance pr_status after validated A2A steps."""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext

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
    transition_to_escalated,
)
from ...state_keys import (
    PLANNER_PLAN_KEY,
    PR_STATUS_KEY,
    PURCHASE_STALL_STREAK_KEY,
    PURCHASE_STEP_SNAPSHOT_KEY,
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
    }
)


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
    "purchase_manager_after_agent",
    "purchase_manager_before_agent",
    "log_purchase_manager_after_agent",
    "log_purchase_manager_before_agent",
]
