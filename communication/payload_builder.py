"""A2A message envelope builder shared by buyer and vendor agents.

Only constructs payload dicts — no business logic, no state management.

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
    envelope = builder.get_quote_payload(quote_id=..., unit_price=...)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .schema import MessageType

_SCHEMA_VERSION = "1.0.0"

# Agent identity constants — use these when constructing the builder so both
# sides share the same canonical string values.
BUYER_AGENT = "buyer_negotiator"
VENDOR_AGENT = "vendor"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _r2(value: float) -> float:
    return round(value, 2)


@dataclass
class A2AMessageBuilder:
    """Builds complete A2A message envelopes for a single RFQ thread.

    Fields common to every message in the thread are set at construction.
    Each ``get_*_payload`` method accepts only the values that vary per turn.

    For buyer → vendor messages use the defaults.
    For vendor → buyer messages pass ``from_agent=VENDOR_AGENT, to_agent=BUYER_AGENT``.
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
            "currency": self.currency,
        }

    def _envelope(
        self,
        message_type: MessageType,
        negotiation_round: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": _SCHEMA_VERSION,
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

    def _priced_envelope(
        self,
        message_type: MessageType,
        unit_price: float,
        negotiation_round: int,
        required_by: str | None,
        response_deadline: str | None,
    ) -> dict[str, Any]:
        def_required_by, def_deadline = self._deadline_defaults()
        item = {**self._base_item()}
        if message_type != MessageType.WALKAWAY:
            item["last_unit_price_offer"] = unit_price
            item["last_total_price_offer"] = _r2(unit_price * self.quantity)
        else:
            item["unit_price"] = unit_price
            item["total_price"] = _r2(unit_price * self.quantity)

        return self._envelope(
            message_type,
            negotiation_round,
            {
                "item": item,
                "required_by": required_by or def_required_by,
                "response_deadline": response_deadline or def_deadline,
            },
        )

    # ── buyer → vendor builders ───────────────────────────────────────────────

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

    def get_counter_offer_payload(
        self,
        unit_price: float,
        negotiation_round: int,
        *,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        return self._priced_envelope(
            MessageType.COUNTER_OFFER, unit_price, negotiation_round, required_by, response_deadline
        )

    def get_accept_payload(
        self,
        unit_price: float,
        negotiation_round: int,
        *,
        required_by: str | None = None,
        response_deadline: str | None = None,
    ) -> dict[str, Any]:
        return self._priced_envelope(
            MessageType.ACCEPT, unit_price, negotiation_round, required_by, response_deadline
        )

    def get_walkaway_payload(
        self,
        walkaway_reason: str,
        negotiation_round: int,
        *,
        last_unit_price: float | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {**self._base_item(), "reason": walkaway_reason}
        if last_unit_price is not None:
            item["last_unit_price"] = last_unit_price
            item["last_total_price"] = _r2(last_unit_price * self.quantity)
        return self._envelope(MessageType.WALKAWAY, negotiation_round, {"item": item})

    # ── vendor → buyer builders ───────────────────────────────────────────────

    def get_quote_payload(
        self,
        unit_price: float,
        negotiation_round: int = 0,
        *,
        valid_until: str = "",
    ) -> dict[str, Any]:
        """Vendor's initial quote response to an RFQ."""
        item: dict[str, Any] = {
            **self._base_item(),
            "unit_price": _r2(unit_price),
            "total_price": _r2(unit_price * self.quantity),
        }

        return self._envelope(
            MessageType.QUOTE,
            negotiation_round,
            {
                "item": item,
                "response_deadline": valid_until,
            },
        )

    def get_counter_response_payload(
        self,
        unit_price: float,
        negotiation_round: int,
        *,
        accepted: bool = False,
        best_and_final: bool = False,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Vendor's response to a buyer counter-offer."""
        item: dict[str, Any] = {
            **self._base_item(),
            "unit_price": _r2(unit_price),
            "total_price": _r2(unit_price * self.quantity),
            "accepted": accepted,
            "best_and_final": best_and_final,
        }
        if message:
            item["message"] = message

        return self._envelope(
            MessageType.COUNTER_RESPONSE,
            negotiation_round,
            {"item": item},
        )
