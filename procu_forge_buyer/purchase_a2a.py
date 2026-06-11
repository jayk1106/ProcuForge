"""Parse and validate vendor A2A replies for the buyer purchase flow."""

from __future__ import annotations

import json
from typing import Any

from communication.schema import MessageType


def parse_vendor_envelope(reply: str) -> dict[str, Any] | None:
    """Return a parsed JSON object when ``reply`` looks like an envelope or ack."""
    stripped = (reply or "").strip()
    if not stripped.startswith("{"):
        return None
    try:
        result = json.loads(stripped)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def vendor_error(envelope: dict[str, Any]) -> str | None:
    """Return an error string when the vendor payload indicates failure."""
    if envelope.get("ok") is False:
        err = envelope.get("error")
        return str(err) if err else "vendor returned ok=false"
    if envelope.get("error") and envelope.get("ok") is not True:
        return str(envelope.get("error"))
    return None


def is_message_type(envelope: dict[str, Any], expected: MessageType) -> bool:
    return str(envelope.get("message_type") or "") == str(expected)


def extract_invoice_payload(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Return invoice fields from an INVOICE_SUBMITTED envelope."""
    if not is_message_type(envelope, MessageType.INVOICE_SUBMITTED):
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return None
    if not payload.get("invoice_number"):
        return None
    return payload


def validate_po_acknowledged(
    envelope: dict[str, Any],
    *,
    expected_po_number: str,
) -> str | None:
    """Return an error string if ``envelope`` is not a valid PO ack."""
    err = vendor_error(envelope)
    if err:
        return err
    if not is_message_type(envelope, MessageType.PO_ACKNOWLEDGED):
        return f"expected PO_ACKNOWLEDGED, got {envelope.get('message_type')!r}"
    payload = envelope.get("payload") or {}
    if not isinstance(payload, dict):
        return "PO_ACKNOWLEDGED missing payload"
    ack_po = str(payload.get("po_number") or "")
    if expected_po_number and ack_po != expected_po_number:
        return f"po_number mismatch: expected {expected_po_number!r}, got {ack_po!r}"
    return None


def validate_invoice_submitted(
    envelope: dict[str, Any],
    *,
    expected_po_number: str | None = None,
    expected_grn_number: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (invoice_payload, error)."""
    err = vendor_error(envelope)
    if err:
        return None, err
    payload = extract_invoice_payload(envelope)
    if payload is None:
        return None, f"expected INVOICE_SUBMITTED, got {envelope.get('message_type')!r}"
    if expected_po_number:
        inv_po = str(payload.get("po_number") or "")
        if inv_po and inv_po != expected_po_number:
            return None, f"invoice po_number mismatch: expected {expected_po_number!r}, got {inv_po!r}"
    if expected_grn_number:
        grn_ref = str(payload.get("grn_reference") or "")
        if grn_ref and grn_ref != expected_grn_number:
            return None, (
                f"invoice grn_reference mismatch: expected {expected_grn_number!r}, got {grn_ref!r}"
            )
    return payload, None


def is_po_rejection(envelope: dict[str, Any]) -> bool:
    """Return True when the vendor explicitly rejected the PO."""
    if envelope.get("ok") is False:
        return True
    msg_type = str(envelope.get("message_type") or "")
    if msg_type in {"PO_REJECTED", "REJECTED"}:
        return True
    payload = envelope.get("payload")
    if isinstance(payload, dict) and payload.get("rejected") is True:
        return True
    return False


def verify_invoice_against_po(
    invoice_payload: dict[str, Any],
    po_record: dict[str, Any],
) -> list[str]:
    """Return a list of mismatch descriptions (empty when invoice matches PO)."""
    mismatches: list[str] = []
    inv_po = str(invoice_payload.get("po_number") or "")
    po_number = str(po_record.get("po_number") or "")
    if inv_po and po_number and inv_po != po_number:
        mismatches.append(f"po_number: expected {po_number!r}, got {inv_po!r}")

    po_total = po_record.get("total_amount")
    inv_total = invoice_payload.get("total_amount") or invoice_payload.get("amount")
    if po_total is not None and inv_total is not None:
        try:
            if abs(float(po_total) - float(inv_total)) > 0.01:
                mismatches.append(
                    f"total_amount: expected {po_total}, got {inv_total}"
                )
        except (TypeError, ValueError):
            mismatches.append("total_amount: non-numeric values")

    po_lines = po_record.get("line_items") or []
    inv_lines = invoice_payload.get("line_items") or []
    if po_lines and inv_lines:
        po_qty = sum(int(item.get("quantity") or 0) for item in po_lines if isinstance(item, dict))
        inv_qty = sum(int(item.get("quantity") or 0) for item in inv_lines if isinstance(item, dict))
        if po_qty and inv_qty and po_qty != inv_qty:
            mismatches.append(f"line quantity: expected {po_qty}, got {inv_qty}")

    return mismatches


def validate_process_complete_ack(envelope: dict[str, Any]) -> str | None:
    """Return an error string unless the vendor ack confirms PROCESS_COMPLETE."""
    err = vendor_error(envelope)
    if err:
        return err
    if envelope.get("ok") is True:
        return None
    return "vendor did not acknowledge PROCESS_COMPLETE with ok=true"


__all__ = [
    "extract_invoice_payload",
    "is_message_type",
    "is_po_rejection",
    "parse_vendor_envelope",
    "validate_invoice_submitted",
    "validate_po_acknowledged",
    "validate_process_complete_ack",
    "vendor_error",
    "verify_invoice_against_po",
]
