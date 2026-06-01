"""Map buyer pr_status values to UI phase labels and human-readable strings."""

from __future__ import annotations

from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.pr_status_transitions import HUMAN_GATED_PR_STATUSES

PhaseLabel = str  # RFQ | NEG | PO | GRN | INV | DONE
PhaseId = str  # rfq | neg | po | grn | inv | done | walked


def parse_pr_status(raw: str | None) -> PrStatus:
    if not raw:
        return PrStatus.INITIATED
    try:
        return PrStatus(raw)
    except ValueError:
        return PrStatus.INITIATED


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
        PrStatus.AWAITING_USER_APPROVAL,
    }:
        return "NEG"
    if status in {PrStatus.PO_ISSUED, PrStatus.PO_ACKNOWLEDGED, PrStatus.PO_REJECTED}:
        return "PO"
    if status in {PrStatus.AWAITING_DELIVERY, PrStatus.GOODS_RECEIVED}:
        return "GRN"
    if status in {
        PrStatus.AWAITING_INVOICE,
        PrStatus.INVOICE_UNDER_VERIFICATION,
        PrStatus.INVOICE_CORRECTION_PENDING,
        PrStatus.INVOICE_VERIFIED,
        PrStatus.READY_FOR_PAYMENT,
    }:
        return "INV"
    if status in {PrStatus.COMPLETED, PrStatus.CANCELLED}:
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
    if status == PrStatus.AWAITING_USER_APPROVAL:
        return "Approve final selection"
    if status == PrStatus.ESCALATED:
        return "Review escalation"
    if status == PrStatus.READY_FOR_PAYMENT:
        return "Authorize payment"
    if status == PrStatus.INVOICE_CORRECTION_PENDING:
        return "Resolve invoice mismatch"
    if status == PrStatus.PO_REJECTED:
        return "Review PO rejection"
    if needs_action(status):
        return "Action required"
    return None


def is_walked_away(status: PrStatus) -> bool:
    return status in {PrStatus.NO_VENDOR_AVAILABLE, PrStatus.NO_VENDORS_DISCOVERED}


def is_completed(status: PrStatus) -> bool:
    return status in {PrStatus.COMPLETED, PrStatus.CANCELLED}


def is_in_progress(status: PrStatus) -> bool:
    return not is_completed(status) and not is_walked_away(status)
