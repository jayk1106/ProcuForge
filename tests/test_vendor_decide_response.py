"""Tests for the vendor's deterministic decide_response tool.

Covers the 9-rule table from the relationship-anchored negotiation refactor:
ACCEPT mirroring, vendor_is_final latching, max-rounds end-states, linear
concession curve, and the floor-final fallback when buyer dips below floor.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from communication import MAX_NEGOTIATION_ROUNDS, MessageType
from procu_forge_vendor.state_keys import (
    LAST_SELLING_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    OPENING_PRICE_KEY,
    ROUND_KEY,
    VENDOR_IS_FINAL_KEY,
)
from procu_forge_vendor.subagents.negotiation.tools import (
    _vendor_target_for,
    decide_response,
)

_OPENING = 950.0
_FLOOR = 900.0


def _state(
    *,
    incoming_envelope: dict,
    previous_offer: float = _OPENING,
    floor: float = _FLOOR,
    opening: float = _OPENING,
    vendor_is_final: bool = False,
    round_state: int = 0,
) -> dict:
    return {
        "temp:request_body": incoming_envelope,
        LATEST_OFFER_PRICE_KEY: previous_offer,
        LAST_SELLING_PRICE_KEY: floor,
        OPENING_PRICE_KEY: opening,
        VENDOR_IS_FINAL_KEY: vendor_is_final,
        ROUND_KEY: round_state,
    }


def _ctx(state: dict) -> MagicMock:
    c = MagicMock()
    c.state = state
    return c


def _counter_offer(price: float, round_n: int) -> dict:
    return {
        "message_type": str(MessageType.COUNTER_OFFER),
        "round": round_n,
        "payload": {"unit_price": price},
    }


def _accept(price: float, round_n: int) -> dict:
    return {
        "message_type": str(MessageType.ACCEPT),
        "round": round_n,
        "payload": {"unit_price": price},
    }


# ── linear curve invariant ──────────────────────────────────────────────────


def test_linear_curve_lands_on_floor_at_max_rounds():
    """vendor_target_for(MAX) == floor and vendor_target_for(0) == opening."""
    assert _vendor_target_for(0, _OPENING, _FLOOR) == _OPENING
    assert _vendor_target_for(MAX_NEGOTIATION_ROUNDS, _OPENING, _FLOOR) == _FLOOR


def test_linear_curve_monotonically_decreases():
    prices = [_vendor_target_for(n, _OPENING, _FLOOR) for n in range(MAX_NEGOTIATION_ROUNDS + 1)]
    for a, b in zip(prices, prices[1:]):
        assert a >= b
    # Strictly decreasing as long as opening > floor.
    assert prices[0] > prices[-1]


# ── buyer ACCEPT rules ───────────────────────────────────────────────────────


def test_buyer_accept_at_floor_returns_accept():
    state = _state(incoming_envelope=_accept(price=_FLOOR, round_n=2))
    out = decide_response(_ctx(state))
    assert out["ok"] is True
    assert out["response_type"] == "ACCEPT"
    assert out["vendor_unit_price"] == _FLOOR


def test_buyer_accept_below_floor_returns_walkaway():
    state = _state(incoming_envelope=_accept(price=_FLOOR - 50, round_n=2))
    out = decide_response(_ctx(state))
    assert out["response_type"] == "WALKAWAY"
    assert out["walkaway_reason"] == "PRICE_GAP_TOO_LARGE"


# ── vendor_is_final latched ──────────────────────────────────────────────────


def test_post_final_buyer_within_floor_accepts():
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR + 10, round_n=3),
        vendor_is_final=True,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "ACCEPT"
    assert out["vendor_unit_price"] == _FLOOR + 10


def test_post_final_buyer_below_floor_walks_away():
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR - 1, round_n=3),
        vendor_is_final=True,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "WALKAWAY"
    assert out["walkaway_reason"] == "PRICE_GAP_TOO_LARGE"


# ── max rounds end states ────────────────────────────────────────────────────


def test_max_rounds_buyer_at_floor_accepts():
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR, round_n=MAX_NEGOTIATION_ROUNDS),
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "ACCEPT"
    assert out["vendor_unit_price"] == _FLOOR


def test_max_rounds_buyer_below_floor_walks_away():
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR - 5, round_n=MAX_NEGOTIATION_ROUNDS),
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "WALKAWAY"
    assert out["walkaway_reason"] == "MAX_ROUNDS_REACHED"


# ── accept-band (rule 7) ─────────────────────────────────────────────────────


def test_buyer_meets_vendor_target_accepts_at_buyer_price():
    target = _vendor_target_for(2, _OPENING, _FLOOR)
    state = _state(
        incoming_envelope=_counter_offer(price=target + 1, round_n=2),
        previous_offer=_OPENING - 10,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "ACCEPT"
    assert out["vendor_unit_price"] == target + 1


# ── floor-final fallback (rule 8) ────────────────────────────────────────────


def test_buyer_below_floor_mid_round_counters_at_floor_final():
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR - 20, round_n=2),
        previous_offer=_OPENING,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "COUNTER_OFFER"
    assert out["vendor_unit_price"] == _FLOOR
    assert out["is_final"] is True


# ── standard linear counter (rule 9) ─────────────────────────────────────────


def test_standard_counter_lands_on_curve():
    # Buyer counters at a price below this round's vendor target — vendor counters
    # at the curve's target for round 2.
    target = _vendor_target_for(2, _OPENING, _FLOOR)
    state = _state(
        incoming_envelope=_counter_offer(price=_FLOOR + 5, round_n=2),
        previous_offer=_OPENING,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "COUNTER_OFFER"
    assert out["vendor_unit_price"] == target
    assert out["is_final"] is False


def test_penultimate_round_marks_is_final():
    state = _state(
        incoming_envelope=_counter_offer(
            price=_FLOOR + 5, round_n=MAX_NEGOTIATION_ROUNDS - 1
        ),
        previous_offer=_OPENING,
    )
    out = decide_response(_ctx(state))
    assert out["response_type"] == "COUNTER_OFFER"
    assert out["is_final"] is True


# ── anchor sanity ────────────────────────────────────────────────────────────


def test_missing_anchors_returns_error():
    state = {
        "temp:request_body": _counter_offer(price=900, round_n=1),
        ROUND_KEY: 1,
    }
    out = decide_response(_ctx(state))
    assert out["ok"] is False
    assert out["error"] == "negotiation_anchors_missing"
