"""A2A message envelope builder shared by buyer and vendor agents.

Constructs envelopes that match `docs/buyer_vendor_communication_reference.md`.
No business logic, no state management.

Usage
-----
Buyer side (default ``from_agent`` / ``to_agent``)::

    builder = A2AMessageBuilder(rfq_id=..., vendor_id=..., ...)
    envelope = builder.get_rfq_payload()

Vendor side (swap directions)::

    builder = A2AMessageBuilder(
        rfq_id=..., vendor_id=..., ...,
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )
    envelope = builder.get_quote_payload(unit_price=...)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .schema import MessageType

# Canonical agent identity constants (envelopes carry agent names only,
# no subagent suffixes — see docs/buyer_vendor_communication_reference.md).
BUYER_AGENT = "buyer_agent"
VENDOR_AGENT = "vendor_agent"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _r2(value: float) -> float:
    return round(value, 2)


@dataclass
class A2AMessageBuilder:
    """Builds complete A2A message envelopes for a single RFQ thread.

    Fields common to every message in the thread are set at construction.
    Each ``get_*_payload`` method accepts only the values that vary per turn.

    For buyer -> vendor messages use the defaults.
    For vendor -> buyer messages pass ``from_agent=VENDOR_AGENT, to_agent=BUYER_AGENT``.
    """

    rfq_id: str
    vendor_id: str
    product_id: str
    sku: str
    quantity: int
    unit: str
    currency: str
    from_agent: str = BUYER_AGENT
    to_agent: str = VENDOR_AGENT

    # ── private ──────────────────────────────────────────────────────────────

    def _base_item(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku": self.sku,
            "quantity": self.quantity,
            "unit": self.unit,
        }

    def _envelope(
        self,
        message_type: MessageType,
        negotiation_round: int | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now()
        return {
            "message_id": str(uuid4()),
            "rfq_id": self.rfq_id,
            "vendor_id": self.vendor_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": str(message_type),
            "round": negotiation_round,
            "timestamp": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "payload": payload,
        }

    @staticmethod
    def _deadline_defaults() -> tuple[str, str]:
        now = _utc_now()
        required_by = (now + timedelta(days=10)).date().isoformat()
        response_deadline = (
            (now + timedelta(days=1))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return required_by, response_deadline

    def _priced_payload(
        self,
        unit_price: float,
        required_by: str | None,
        response_deadline: str | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a payload with top-level prices + item block.

        Used by QUOTE, COUNTER_OFFER, ACCEPT.
        """
        def_required_by, def_deadline = self._deadline_defaults()
        payload: dict[str, Any] = {
            "item": self._base_item(),
            "unit_price": _r2(unit_price),
            "total_price": _r2(unit_price * self.quantity),
            "currency": self.currency,
            "required_by": required_by or def_required_by,
            "response_deadline": response_deadline or def_deadline,
        }
        if extra:
            payload.update(extra)
        return payload

    # ── RFQ (buyer -> vendor) ────────────────────────────────────────────────

    def get_rfq_payload(
        self,
        negotiation_round: int = 0,
        *,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        def_required_by, def_deadline = self._deadline_defaults()
        return self._envelope(
            MessageType.RFQ,
            negotiation_round,
            {
                "item": self._base_item(),
                "required_by": required_by or def_required_by,
                "response_deadline": response_deadline or def_deadline,
            },
        )

    # ── QUOTE (vendor -> buyer) ──────────────────────────────────────────────

    def get_quote_payload(
        self,
        unit_price: float,
        negotiation_round: int = 0,
        *,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        """Vendor's initial quote response to an RFQ."""
        return self._envelope(
            MessageType.QUOTE,
            negotiation_round,
            self._priced_payload(unit_price, required_by, response_deadline),
        )

    # ── COUNTER_OFFER (both directions) ──────────────────────────────────────

    def get_counter_offer_payload(
        self,
        unit_price: float,
        negotiation_round: int,
        *,
        is_final: bool = False,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        """Counter offer in either direction (buyer -> vendor or vendor -> buyer)."""
        return self._envelope(
            MessageType.COUNTER_OFFER,
            negotiation_round,
            self._priced_payload(
                unit_price,
                required_by,
                response_deadline,
                extra={"is_final": is_final},
            ),
        )

    # ── ACCEPT (both directions) ─────────────────────────────────────────────

    def get_accept_payload(
        self,
        unit_price: float,
        negotiation_round: int,
        *,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        return self._envelope(
            MessageType.ACCEPT,
            negotiation_round,
            self._priced_payload(unit_price, required_by, response_deadline),
        )

    # ── WALKAWAY (both directions) ───────────────────────────────────────────

    def get_walkaway_payload(
        self,
        walkaway_reason: str,
        negotiation_round: int,
        *,
        last_unit_price: float | None = None,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        def_required_by, def_deadline = self._deadline_defaults()
        payload: dict[str, Any] = {
            "item": self._base_item(),
            "reason": walkaway_reason,
            "required_by": required_by or def_required_by,
            "response_deadline": response_deadline or def_deadline,
        }
        if last_unit_price is not None:
            payload["last_unit_price"] = _r2(last_unit_price)
            payload["last_total_price"] = _r2(last_unit_price * self.quantity)
        return self._envelope(MessageType.WALKAWAY, negotiation_round, payload)

    # ── RFQ_CLOSED (buyer -> vendor) ─────────────────────────────────────────

    def get_rfq_closed_payload(
        self,
        outcome: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._envelope(
            MessageType.RFQ_CLOSED,
            None,
            {
                "item": self._base_item(),
                "outcome": outcome,
                "reason": reason,
            },
        )

    # ── PO (buyer -> vendor) ─────────────────────────────────────────────────

    def get_po_payload(
        self,
        po_number: str,
        rfq_reference: str,
        line_items: list[dict[str, Any]],
        total_amount: float,
        delivery_date: str,
    ) -> dict[str, Any]:
        """Purchase order. Line items use ``total_price`` per line (not ``line_total``)."""
        return self._envelope(
            MessageType.PO,
            None,
            {
                "po_number": po_number,
                "rfq_reference": rfq_reference,
                "line_items": line_items,
                "total_amount": _r2(total_amount),
                "currency": self.currency,
                "delivery_date": delivery_date,
            },
        )

    # ── PO_ACKNOWLEDGED (vendor -> buyer) ────────────────────────────────────

    def get_po_acknowledged_payload(self, po_number: str) -> dict[str, Any]:
        """Slim ack — only ``po_number`` per reference doc."""
        return self._envelope(
            MessageType.PO_ACKNOWLEDGED,
            None,
            {"po_number": po_number},
        )

    # ── GRN_CREATED (buyer -> vendor) ────────────────────────────────────────

    def get_grn_created_payload(
        self,
        grn_number: str,
        po_number: str,
        received_at: str,
        line_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Goods receipt note. Line items use ``{ sku, unit_quantity }``."""
        return self._envelope(
            MessageType.GRN_CREATED,
            None,
            {
                "grn_number": grn_number,
                "po_number": po_number,
                "received_at": received_at,
                "line_items": line_items,
            },
        )

    # ── INVOICE_SUBMITTED (vendor -> buyer) ──────────────────────────────────

    def get_invoice_submitted_payload(
        self,
        invoice_number: str,
        po_number: str,
        invoice_date: str,
        line_items: list[dict[str, Any]],
        total_amount: float,
        *,
        grn_reference: str | None = None,
        due_date: str | None = None,
    ) -> dict[str, Any]:
        """Vendor invoice. Line items use ``total_price``; no subtotal/tax/payment_terms."""
        payload: dict[str, Any] = {
            "invoice_number": invoice_number,
            "po_number": po_number,
            "invoice_date": invoice_date,
            "line_items": line_items,
            "total_amount": _r2(total_amount),
            "currency": self.currency,
        }
        if grn_reference:
            payload["grn_reference"] = grn_reference
        if due_date:
            payload["due_date"] = due_date
        return self._envelope(MessageType.INVOICE_SUBMITTED, None, payload)

    # ── PROCESS_COMPLETE (buyer -> vendor) ───────────────────────────────────

    def get_process_complete_payload(
        self,
        po_number: str,
        grn_number: str,
        invoice_number: str,
    ) -> dict[str, Any]:
        return self._envelope(
            MessageType.PROCESS_COMPLETE,
            None,
            {
                "po_number": po_number,
                "grn_number": grn_number,
                "invoice_number": invoice_number,
            },
        )
