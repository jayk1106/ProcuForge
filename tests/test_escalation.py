"""Tests for procu_forge_buyer.escalation helpers."""

from __future__ import annotations

from procu_forge_buyer.escalation import maybe_escalate_full, maybe_notify_only
from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    PR_STATUS_KEY,
)


def test_maybe_notify_only_keeps_terminal_status():
    state = {PR_STATUS_KEY: PrStatus.NO_VENDORS_DISCOVERED.value}
    maybe_notify_only(
        state,
        source="no_vendors_discovered",
        reason="No suppliers found",
    )
    assert state[PR_STATUS_KEY] == PrStatus.NO_VENDORS_DISCOVERED.value
    assert state[ESCALATION_PENDING_NOTIFY_KEY] is True
    ctx = state[ESCALATION_CONTEXT_KEY]
    assert ctx["tier"] == "notify_only"
    assert ctx["source"] == "no_vendors_discovered"
    assert ctx["reason"] == "No suppliers found"


def test_maybe_escalate_full_sets_escalated():
    state = {PR_STATUS_KEY: PrStatus.NEGOTIATION_IN_PROGRESS.value}
    maybe_escalate_full(
        state,
        source="negotiator_stall",
        reason="Stalled",
    )
    assert state[PR_STATUS_KEY] == PrStatus.ESCALATED.value
    assert state[ESCALATION_CONTEXT_KEY]["tier"] == "full"


def test_maybe_notify_only_is_idempotent():
    state = {PR_STATUS_KEY: PrStatus.NO_VENDOR_AVAILABLE.value}
    maybe_notify_only(state, source="no_vendor_available", reason="first")
    first = dict(state[ESCALATION_CONTEXT_KEY])
    maybe_notify_only(state, source="no_vendor_available", reason="second")
    assert state[ESCALATION_CONTEXT_KEY] == first


def test_maybe_escalate_full_falls_back_to_notify_on_terminal():
    state = {PR_STATUS_KEY: PrStatus.NO_VENDOR_AVAILABLE.value}
    maybe_escalate_full(state, source="loop_exhausted", reason="stuck")
    assert state[PR_STATUS_KEY] == PrStatus.NO_VENDOR_AVAILABLE.value
    assert state[ESCALATION_CONTEXT_KEY]["tier"] == "notify_only"
