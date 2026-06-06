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
    "parse_vendor_envelope",
    "validate_invoice_submitted",
    "validate_po_acknowledged",
    "validate_process_complete_ack",
    "vendor_error",
]
