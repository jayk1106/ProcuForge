"""Shared enums for buyer-side agents (see ``schema/communication.json``)."""

from __future__ import annotations

from enum import StrEnum


class MessageType(StrEnum):
    """A2A envelope ``message_type`` values."""

    RFQ = "RFQ"
    QUOTE = "QUOTE"
    COUNTER_OFFER = "COUNTER_OFFER"
    COUNTER_RESPONSE = "COUNTER_RESPONSE"
    ACCEPT = "ACCEPT"
    WALKAWAY = "WALKAWAY"
    VENDOR_SELECTED = "VENDOR_SELECTED"
    RFQ_CLOSED = "RFQ_CLOSED"
    PO = "PO"
    PO_ACKNOWLEDGED = "PO_ACKNOWLEDGED"
    GRN_CREATED = "GRN_CREATED"
    INVOICE_SUBMITTED = "INVOICE_SUBMITTED"
    INVOICE_VERIFICATION_RESULT = "INVOICE_VERIFICATION_RESULT"
    INVOICE_CORRECTED = "INVOICE_CORRECTED"
    PROCESS_COMPLETE = "PROCESS_COMPLETE"


__all__ = ["MessageType"]
