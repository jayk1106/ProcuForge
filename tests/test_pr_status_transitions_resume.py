"""Tests for HITL gate and resume transitions in pr_status_transitions."""

from __future__ import annotations

from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.pr_status_transitions import (
    HUMAN_GATED_PR_STATUSES,
    STOP_PR_STATUSES,
    transition_resume_for_completion,
    transition_resume_for_grn,
    transition_resume_for_po,
    transition_to_awaiting_completion_approval,
    transition_to_awaiting_grn_approval,
    transition_to_awaiting_po_approval,
)
from procu_forge_buyer.state_keys import PR_STATUS_KEY, PREVIOUS_PR_STATUS_KEY


def test_gates_in_human_gated_set():
    assert PrStatus.AWAITING_PO_APPROVAL in HUMAN_GATED_PR_STATUSES
    assert PrStatus.AWAITING_GRN_APPROVAL in HUMAN_GATED_PR_STATUSES
    assert PrStatus.AWAITING_COMPLETION_APPROVAL in HUMAN_GATED_PR_STATUSES
    # STOP set derives from HUMAN_GATED — verify propagation.
    assert PrStatus.AWAITING_PO_APPROVAL in STOP_PR_STATUSES
    assert PrStatus.AWAITING_GRN_APPROVAL in STOP_PR_STATUSES
    assert PrStatus.AWAITING_COMPLETION_APPROVAL in STOP_PR_STATUSES


def test_transition_to_awaiting_po_approval_only_from_vendor_selected():
    state = {PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value}
    transition_to_awaiting_po_approval(state)
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_PO_APPROVAL.value
    assert state[PREVIOUS_PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value

    # Idempotent — called twice does not break.
    transition_to_awaiting_po_approval(state)
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_PO_APPROVAL.value

    # Refuses to move from an unrelated source status.
    state2 = {PR_STATUS_KEY: PrStatus.PO_ISSUED.value}
    transition_to_awaiting_po_approval(state2)
    assert state2[PR_STATUS_KEY] == PrStatus.PO_ISSUED.value


def test_transition_to_awaiting_grn_approval_only_from_po_acknowledged():
    state = {PR_STATUS_KEY: PrStatus.PO_ACKNOWLEDGED.value}
    transition_to_awaiting_grn_approval(state)
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_GRN_APPROVAL.value

    state2 = {PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value}
    transition_to_awaiting_grn_approval(state2)
    assert state2[PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value


def test_transition_to_awaiting_completion_approval_only_from_invoice_phase():
    state = {PR_STATUS_KEY: PrStatus.INVOICE_UNDER_VERIFICATION.value}
    transition_to_awaiting_completion_approval(state)
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_COMPLETION_APPROVAL.value

    state2 = {PR_STATUS_KEY: PrStatus.PO_ACKNOWLEDGED.value}
    transition_to_awaiting_completion_approval(state2)
    assert state2[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value


def test_resume_helpers_flip_back_to_active_status():
    state = {PR_STATUS_KEY: PrStatus.AWAITING_PO_APPROVAL.value}
    transition_resume_for_po(state)
    assert state[PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value

    state = {PR_STATUS_KEY: PrStatus.AWAITING_GRN_APPROVAL.value}
    transition_resume_for_grn(state)
    assert state[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value

    state = {PR_STATUS_KEY: PrStatus.AWAITING_COMPLETION_APPROVAL.value}
    transition_resume_for_completion(state)
    assert state[PR_STATUS_KEY] == PrStatus.INVOICE_UNDER_VERIFICATION.value


def test_resume_helpers_noop_when_not_at_matching_gate():
    state = {PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value}
    transition_resume_for_po(state)
    assert state[PR_STATUS_KEY] == PrStatus.VENDOR_SELECTED.value

    state = {PR_STATUS_KEY: PrStatus.AWAITING_PO_APPROVAL.value}
    transition_resume_for_grn(state)
    assert state[PR_STATUS_KEY] == PrStatus.AWAITING_PO_APPROVAL.value
