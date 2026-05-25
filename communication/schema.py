"""A2A message type enum (see schema/communication.json)."""

from __future__ import annotations

from enum import StrEnum


class MessageType(StrEnum):
    """A2A envelope ``message_type`` values."""

    RFQ = "RFQ"
    QUOTE = "QUOTE"
    COUNTER_OFFER = "COUNTER_OFFER"
    ACCEPT = "ACCEPT"
    WALKAWAY = "WALKAWAY"
    RFQ_CLOSED = "RFQ_CLOSED"
    PO = "PO"
    PO_ACKNOWLEDGED = "PO_ACKNOWLEDGED"
    GRN_CREATED = "GRN_CREATED"
    INVOICE_SUBMITTED = "INVOICE_SUBMITTED"
    PROCESS_COMPLETE = "PROCESS_COMPLETE"


__all__ = ["MessageType"]
