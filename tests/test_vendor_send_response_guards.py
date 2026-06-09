"""Tests for the hardened send_response guards on the vendor side.

The previously-missing ``counter_above_previous_offer`` guard is the direct fix
for the symptom that motivated this refactor (vendor occasionally countered at a
price ABOVE its own previous quote). These tests pin that and the new
``counter_below_buyer_price`` guard.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from procu_forge_vendor.state_keys import (
    LAST_SELLING_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    VENDOR_ID_KEY,
)
from procu_forge_vendor.subagents.negotiation.tools import send_response


def _base_state(*, previous_offer: float, floor: float) -> dict:
    return {
        VENDOR_ID_KEY: "vendor-1",
        RFQ_ID_KEY: "rfq-1",
        PRODUCT_KEY: {
            "id": "prod-1",
            "sku": "SKU-1",
            "currency": "USD",
            "unit": "unit",
            "quantity": 1,
            "listed_unit_price": 1000.0,
        },
        LATEST_OFFER_PRICE_KEY: previous_offer,
        LAST_SELLING_PRICE_KEY: floor,
        "temp:request_body": {"round": 1, "payload": {}},
    }


def _ctx(state: dict) -> MagicMock:
    c = MagicMock()
    c.state = state
    return c


def test_counter_above_previous_offer_rejected():
    """The bug fix: vendor cannot counter at >= its own previous quote."""
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="COUNTER_OFFER",
        vendor_unit_price=960.0,   # ABOVE previous offer
        buyer_proposed_price=800.0,
        tool_context=_ctx(state),
    )
    assert result["ok"] is False
    assert result["error"] == "counter_above_previous_offer"
    assert "previous_offer" in result


def test_counter_equal_to_previous_offer_rejected():
    """Edge: counter == previous offer is also not a concession."""
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="COUNTER_OFFER",
        vendor_unit_price=950.0,
        buyer_proposed_price=800.0,
        tool_context=_ctx(state),
    )
    assert result["ok"] is False
    assert result["error"] == "counter_above_previous_offer"


def test_counter_below_buyer_price_rejected():
    """A counter must sit strictly above the buyer's bid — otherwise just ACCEPT."""
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="COUNTER_OFFER",
        vendor_unit_price=920.0,
        buyer_proposed_price=925.0,   # buyer is ABOVE the proposed counter
        tool_context=_ctx(state),
    )
    assert result["ok"] is False
    assert result["error"] == "counter_below_buyer_price"


def test_counter_below_floor_rejected():
    """Existing floor guard still fires after the refactor."""
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="COUNTER_OFFER",
        vendor_unit_price=850.0,   # below floor
        buyer_proposed_price=800.0,
        tool_context=_ctx(state),
    )
    assert result["ok"] is False
    assert result["error"] == "floor_price_violation"


def test_valid_counter_passes_all_guards():
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="COUNTER_OFFER",
        vendor_unit_price=930.0,   # floor <= price < previous_offer, > buyer_price
        buyer_proposed_price=900.0,
        tool_context=_ctx(state),
    )
    assert result["ok"] is True
    assert result["message_type"] == "COUNTER_OFFER"
    # Outbound envelope queued.
    assert state["temp:response_body"]["payload"]["unit_price"] == 930.0
    # State updated for next round.
    assert state[LATEST_OFFER_PRICE_KEY] == 930.0


def test_accept_bypasses_counter_guards():
    """ACCEPT can be at any historically-valid price — counter guards don't apply."""
    state = _base_state(previous_offer=950.0, floor=900.0)
    result = send_response(
        response_type="ACCEPT",
        vendor_unit_price=950.0,
        buyer_proposed_price=950.0,
        tool_context=_ctx(state),
    )
    assert result["ok"] is True
    assert result["message_type"] == "ACCEPT"
