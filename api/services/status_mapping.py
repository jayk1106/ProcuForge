"""Map buyer pr_status values to UI phase labels and human-readable strings."""

from __future__ import annotations

from typing import Any

from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.pr_status_transitions import HUMAN_GATED_PR_STATUSES
from procu_forge_buyer.state_keys import (
    INVOICE_VENDOR_ACK_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
)

PhaseLabel = str  # RFQ | NEG | PO | GRN | INV | DONE
PhaseId = str  # rfq | neg | po | grn | inv | done | walked


def parse_pr_status(raw: str | None) -> PrStatus:
    if not raw:
        return PrStatus.INITIATED
    try:
        return PrStatus(raw)
    except ValueError:
        return PrStatus.INITIATED


def effective_pr_status(state: dict[str, Any]) -> PrStatus:
    """Return UI-facing status, inferring from vendor ack keys when ``pr_status`` lags."""
    stored = parse_pr_status(state.get(PR_STATUS_KEY))
    if stored in {PrStatus.COMPLETED, PrStatus.CANCELLED, PrStatus.ESCALATED}:
        return stored
    # HITL gates are authoritative — do not let ack keys infer past a parked
    # status (e.g. AWAITING_GRN_APPROVAL sits on top of an existing po_vendor_ack).
    if stored in {
        PrStatus.AWAITING_PO_APPROVAL,
        PrStatus.AWAITING_GRN_APPROVAL,
        PrStatus.AWAITING_COMPLETION_APPROVAL,
    }:
        return stored
    if state.get(PROCESS_COMPLETE_VENDOR_ACK_KEY):
        return PrStatus.COMPLETED
    if state.get(INVOICE_VENDOR_ACK_KEY):
        return PrStatus.INVOICE_UNDER_VERIFICATION
    if state.get(PO_VENDOR_ACK_KEY):
        return PrStatus.PO_ACKNOWLEDGED
    return stored


def pr_status_to_phase_label(status: PrStatus) -> PhaseLabel:
    if status in {
        PrStatus.INITIATED,
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NO_VENDORS_DISCOVERED,
    }:
        return "RFQ"
    if status in {
        PrStatus.NEGOTIATION_IN_PROGRESS,
        PrStatus.NEGOTIATION_COMPLETED,
        PrStatus.VENDOR_SELECTED,
        PrStatus.NO_VENDOR_AVAILABLE,
    }:
        return "NEG"
    if status in {
        PrStatus.AWAITING_USER_APPROVAL,
        PrStatus.AWAITING_PO_APPROVAL,
        PrStatus.PO_ISSUED,
        PrStatus.PO_ACKNOWLEDGED,
        PrStatus.PO_REJECTED,
    }:
        return "PO"
    if status in {
        PrStatus.AWAITING_DELIVERY,
        PrStatus.GOODS_RECEIVED,
        PrStatus.AWAITING_GRN_APPROVAL,
    }:
        return "GRN"
    if status in {
        PrStatus.AWAITING_INVOICE,
        PrStatus.INVOICE_UNDER_VERIFICATION,
        PrStatus.INVOICE_CORRECTION_PENDING,
        PrStatus.INVOICE_VERIFIED,
        PrStatus.READY_FOR_PAYMENT,
    }:
        return "INV"
    if status in {
        PrStatus.COMPLETED,
        PrStatus.CANCELLED,
        PrStatus.AWAITING_COMPLETION_APPROVAL,
    }:
        return "DONE"
    if status == PrStatus.ESCALATED:
        return "NEG"
    return "RFQ"


def pr_status_to_phase_id(status: PrStatus) -> PhaseId:
    label = pr_status_to_phase_label(status)
    if status == PrStatus.NO_VENDOR_AVAILABLE:
        return "walked"
    mapping = {
        "RFQ": "rfq",
        "NEG": "neg",
        "PO": "po",
        "GRN": "grn",
        "INV": "inv",
        "DONE": "done",
    }
    return mapping.get(label, "rfq")


_PR_STATUS_LABELS: dict[PrStatus, str] = {
    PrStatus.INITIATED: "Initiated",
    PrStatus.VENDORS_DISCOVERED: "Vendors Discovered",
    PrStatus.NO_VENDORS_DISCOVERED: "No Vendors Discovered",
    PrStatus.NEGOTIATION_IN_PROGRESS: "Negotiation In Progress",
    PrStatus.NEGOTIATION_COMPLETED: "Negotiation Completed",
    PrStatus.VENDOR_SELECTED: "Vendor Selected",
    PrStatus.NO_VENDOR_AVAILABLE: "No Vendor Available",
    PrStatus.AWAITING_USER_APPROVAL: "Awaiting User Approval",
    PrStatus.AWAITING_PO_APPROVAL: "Awaiting PO Approval",
    PrStatus.AWAITING_GRN_APPROVAL: "Awaiting GRN Approval",
    PrStatus.AWAITING_COMPLETION_APPROVAL: "Awaiting Completion Approval",
    PrStatus.PO_ISSUED: "PO Issued",
    PrStatus.PO_ACKNOWLEDGED: "PO Acknowledged",
    PrStatus.PO_REJECTED: "PO Rejected",
    PrStatus.AWAITING_DELIVERY: "Awaiting Delivery",
    PrStatus.GOODS_RECEIVED: "Goods Received",
    PrStatus.AWAITING_INVOICE: "Awaiting Invoice",
    PrStatus.INVOICE_UNDER_VERIFICATION: "Invoice Under Verification",
    PrStatus.INVOICE_CORRECTION_PENDING: "Invoice Correction Pending",
    PrStatus.INVOICE_VERIFIED: "Invoice Verified",
    PrStatus.READY_FOR_PAYMENT: "Ready for Payment",
    PrStatus.COMPLETED: "Completed",
    PrStatus.CANCELLED: "Cancelled",
    PrStatus.ESCALATED: "Escalated",
}


def pr_status_human_label(status: PrStatus) -> str:
    return _PR_STATUS_LABELS.get(status, status.value.replace("_", " ").title())


def needs_action(status: PrStatus) -> bool:
    return status in HUMAN_GATED_PR_STATUSES


def action_label(status: PrStatus) -> str | None:
    if status == PrStatus.ESCALATED:
        return "Review escalation"
    if status == PrStatus.READY_FOR_PAYMENT:
        return "Authorize payment"
    if status == PrStatus.INVOICE_CORRECTION_PENDING:
        return "Resolve invoice mismatch"
    if status == PrStatus.PO_REJECTED:
        return "Review PO rejection"
    if status == PrStatus.AWAITING_PO_APPROVAL:
        return "Approve & send PO"
    if status == PrStatus.AWAITING_GRN_APPROVAL:
        return "Approve & send GRN"
    if status == PrStatus.AWAITING_COMPLETION_APPROVAL:
        return "Approve & close procurement"
    if needs_action(status):
        return "Action required"
    return None


def is_walked_away(status: PrStatus) -> bool:
    return status in {PrStatus.NO_VENDOR_AVAILABLE, PrStatus.NO_VENDORS_DISCOVERED}


def is_completed(status: PrStatus) -> bool:
    return status in {PrStatus.COMPLETED, PrStatus.CANCELLED}


def is_in_progress(status: PrStatus) -> bool:
    return not is_completed(status) and not is_walked_away(status)


PhaseStatus = str  # pending | in_progress | done | walked

PHASE_ORDER: tuple[PhaseId, ...] = ("rfq", "neg", "po", "grn", "inv", "done")


def phase_status_map(status: PrStatus) -> dict[PhaseId, PhaseStatus]:
    """Return per-phase status for the timeline / sidebar.

    Values: ``pending`` | ``in_progress`` | ``done`` | ``walked``.
    Phases before the current phase are ``done``; the current phase is
    ``in_progress``; phases after are ``pending``. Terminal/failure statuses
    mark the failing phase ``walked``.
    """
    if status == PrStatus.COMPLETED:
        return {p: "done" for p in PHASE_ORDER}

    if status == PrStatus.NO_VENDORS_DISCOVERED:
        result: dict[PhaseId, PhaseStatus] = {p: "pending" for p in PHASE_ORDER}
        result["rfq"] = "walked"
        return result

    if status == PrStatus.NO_VENDOR_AVAILABLE:
        result = {p: "pending" for p in PHASE_ORDER}
        result["rfq"] = "done"
        result["neg"] = "walked"
        return result

    if status == PrStatus.PO_REJECTED:
        result = {p: "pending" for p in PHASE_ORDER}
        result["rfq"] = "done"
        result["neg"] = "done"
        result["po"] = "walked"
        return result

    current = pr_status_to_phase_id(status)
    if status == PrStatus.CANCELLED:
        result = {}
        passed = False
        for p in PHASE_ORDER:
            if p == current:
                result[p] = "walked"
                passed = True
            elif not passed:
                result[p] = "done"
            else:
                result[p] = "pending"
        return result

    result = {}
    passed = False
    for p in PHASE_ORDER:
        if p == current:
            result[p] = "in_progress"
            passed = True
        elif not passed:
            result[p] = "done"
        else:
            result[p] = "pending"
    return result


def spec_done(status: PrStatus) -> bool:
    """Specification (step 1.0 in the sidebar) is validated as soon as the
    workflow has progressed past INITIATED.
    """
    return status != PrStatus.INITIATED
