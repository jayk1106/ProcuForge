"""Tests for PO rejection and invoice verification escalation paths."""

from __future__ import annotations

from procu_forge_buyer.purchase_a2a import is_po_rejection, verify_invoice_against_po


def test_is_po_rejection_detects_ok_false():
    assert is_po_rejection({"ok": False, "error": "rejected"}) is True


def test_verify_invoice_against_po_detects_total_mismatch():
    mismatches = verify_invoice_against_po(
        {"po_number": "PO-1", "total_amount": 100.0},
        {"po_number": "PO-1", "total_amount": 120.0, "line_items": [{"quantity": 2}]},
    )
    assert any("total_amount" in m for m in mismatches)


def test_verify_invoice_against_po_empty_when_match():
    mismatches = verify_invoice_against_po(
        {"po_number": "PO-1", "total_amount": 120.0, "line_items": [{"quantity": 2}]},
        {"po_number": "PO-1", "total_amount": 120.0, "line_items": [{"quantity": 2}]},
    )
    assert mismatches == []
