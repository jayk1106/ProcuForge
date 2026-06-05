"""Tests for purchase A2A reply parsing and validation."""

from __future__ import annotations

import json

from communication.schema import MessageType
from procu_forge_buyer.purchase_a2a import (
    parse_vendor_envelope,
    validate_invoice_submitted,
    validate_po_acknowledged,
    validate_process_complete_ack,
    vendor_error,
)


def test_parse_vendor_envelope_ok():
    raw = json.dumps({"message_type": "PO_ACKNOWLEDGED", "payload": {"po_number": "PO-1"}})
    env = parse_vendor_envelope(raw)
    assert env is not None
    assert env["message_type"] == "PO_ACKNOWLEDGED"


def test_vendor_error_from_ok_false():
    assert vendor_error({"ok": False, "error": "process_complete_out_of_order"}) == (
        "process_complete_out_of_order"
    )


def test_validate_po_acknowledged_success():
    env = {
        "message_type": "PO_ACKNOWLEDGED",
        "payload": {"po_number": "PO-ABC"},
    }
    assert validate_po_acknowledged(env, expected_po_number="PO-ABC") is None


def test_validate_po_acknowledged_mismatch():
    env = {
        "message_type": "PO_ACKNOWLEDGED",
        "payload": {"po_number": "PO-OTHER"},
    }
    err = validate_po_acknowledged(env, expected_po_number="PO-ABC")
    assert err and "mismatch" in err


def test_validate_invoice_submitted_success():
    env = {
        "message_type": "INVOICE_SUBMITTED",
        "payload": {
            "invoice_number": "INV-1",
            "po_number": "PO-1",
            "grn_reference": "GRN-1",
        },
    }
    payload, err = validate_invoice_submitted(
        env, expected_po_number="PO-1", expected_grn_number="GRN-1"
    )
    assert err is None
    assert payload["invoice_number"] == "INV-1"


def test_validate_process_complete_ack_success():
    assert validate_process_complete_ack({"ok": True, "status": "COMPLETE"}) is None


def test_validate_process_complete_ack_failure():
    err = validate_process_complete_ack(
        {"ok": False, "error": "process_complete_out_of_order", "current_status": "ACCEPTED"}
    )
    assert err == "process_complete_out_of_order"
