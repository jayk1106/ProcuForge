from __future__ import annotations

from typing import Any, Literal

from google.adk.tools.base_tool import ToolContext

from communication import MAX_NEGOTIATION_ROUNDS, A2AMessageBuilder, MessageType
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_vendor.state_keys import (
    LAST_SELLING_PRICE_KEY,
    LATEST_BUYER_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    OPENING_PRICE_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    ROUND_KEY,
    VENDOR_ID_KEY,
    VENDOR_IS_FINAL_KEY,
)

_PRICE_EPSILON = 0.01


# ── shared helpers ──────────────────────────────────────────────────────────


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vendor_target_for(round_n: int, opening_price: float, floor_price: float) -> float:
    """Linear concession curve: target at round n along the line opening -> floor.

    Round 0 returns ``opening_price``; round MAX_NEGOTIATION_ROUNDS returns ``floor_price``.
    The vendor sends a counter at this price for buyer round ``round_n``.
    """
    if MAX_NEGOTIATION_ROUNDS <= 0:
        return floor_price
    step = (opening_price - floor_price) / MAX_NEGOTIATION_ROUNDS
    target = opening_price - round_n * step
    return round(max(target, floor_price), 2)


def _incoming_envelope(state: Any) -> dict[str, Any]:
    body = state.get("temp:request_body")
    return body if isinstance(body, dict) else {}


def _extract_buyer_price(envelope: dict[str, Any]) -> float | None:
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    msg_type = str(envelope.get("message_type") or "")
    if msg_type == str(MessageType.WALKAWAY):
        return _to_float(payload.get("last_unit_price"))
    return _to_float(payload.get("unit_price"))


# ── decide_response ──────────────────────────────────────────────────────────


def decide_response(tool_context: ToolContext) -> dict[str, Any]:
    """Compute the vendor's next move deterministically.

    Mirror of the buyer's ``_decide_next_move`` at
    ``procu_forge_buyer/subagents/negotiator/tools.py``. The LLM should pass
    the returned ``{response_type, vendor_unit_price?, is_final, walkaway_reason?}``
    fields straight into ``send_response`` — it does NOT pick prices itself.

    Returns ``{"ok": True, "response_type": ..., ...}`` on success, or
    ``{"ok": False, "error": ...}`` if the negotiation thread isn't set up yet
    (e.g. quote_agent didn't seed anchors).
    """
    envelope = _incoming_envelope(tool_context.state)
    if not envelope:
        return {"ok": False, "error": "no inbound buyer message in state"}

    floor_price = _to_float(tool_context.state.get(LAST_SELLING_PRICE_KEY))
    opening_price = _to_float(tool_context.state.get(OPENING_PRICE_KEY))
    previous_offer = _to_float(tool_context.state.get(LATEST_OFFER_PRICE_KEY))

    if floor_price is None or opening_price is None:
        return {
            "ok": False,
            "error": "negotiation_anchors_missing",
            "hint": "quote_agent must run first to seed last_selling_price and opening_price",
        }

    incoming_round_raw = envelope.get("round")
    try:
        round_n = int(incoming_round_raw) if incoming_round_raw is not None else int(
            tool_context.state.get(ROUND_KEY) or 0
        )
    except (TypeError, ValueError):
        round_n = int(tool_context.state.get(ROUND_KEY) or 0)

    vendor_is_final = bool(tool_context.state.get(VENDOR_IS_FINAL_KEY))
    msg_type = str(envelope.get("message_type") or "")
    buyer_price = _extract_buyer_price(envelope)

    # Rule 1/2: buyer ACCEPT — mirror it if at or above floor; walk away below.
    if msg_type == str(MessageType.ACCEPT) and buyer_price is not None:
        if buyer_price >= floor_price - _PRICE_EPSILON:
            return {
                "ok": True,
                "response_type": "ACCEPT",
                "vendor_unit_price": round(buyer_price, 2),
                "buyer_proposed_price": round(buyer_price, 2),
                "is_final": False,
                "reason": "buyer_accept_at_or_above_floor",
            }
        return {
            "ok": True,
            "response_type": "WALKAWAY",
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": False,
            "reason": "buyer_accept_below_floor",
        }

    # COUNTER_OFFER and other priced messages need a buyer price to reason about.
    if buyer_price is None:
        # Buyer envelope without a price (e.g. WALKAWAY with no last_unit_price). Walk away.
        return {
            "ok": True,
            "response_type": "WALKAWAY",
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "is_final": False,
            "reason": "buyer_envelope_missing_price",
        }

    buyer_within_floor = buyer_price >= floor_price - _PRICE_EPSILON

    # Rule 3/4: vendor already declared best-and-final. Only ACCEPT or WALKAWAY.
    if vendor_is_final:
        if buyer_within_floor:
            return {
                "ok": True,
                "response_type": "ACCEPT",
                "vendor_unit_price": round(max(buyer_price, floor_price), 2),
                "buyer_proposed_price": round(buyer_price, 2),
                "is_final": False,
                "reason": "post_final_buyer_within_floor",
            }
        return {
            "ok": True,
            "response_type": "WALKAWAY",
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": False,
            "reason": "post_final_buyer_below_floor",
        }

    # Rule 5/6: rounds exhausted.
    if round_n >= MAX_NEGOTIATION_ROUNDS:
        if buyer_within_floor:
            return {
                "ok": True,
                "response_type": "ACCEPT",
                "vendor_unit_price": round(max(buyer_price, floor_price), 2),
                "buyer_proposed_price": round(buyer_price, 2),
                "is_final": False,
                "reason": "max_rounds_buyer_within_floor",
            }
        return {
            "ok": True,
            "response_type": "WALKAWAY",
            "walkaway_reason": "MAX_ROUNDS_REACHED",
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": False,
            "reason": "max_rounds_buyer_below_floor",
        }

    vendor_target = _vendor_target_for(round_n, opening_price, floor_price)

    # Rule 7: buyer has met or beaten this round's vendor target — accept their price.
    if buyer_price >= vendor_target - _PRICE_EPSILON and buyer_within_floor:
        return {
            "ok": True,
            "response_type": "ACCEPT",
            "vendor_unit_price": round(buyer_price, 2),
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": False,
            "reason": "buyer_at_or_above_target",
        }

    # Rule 8: buyer is below floor on a non-terminal round — counter AT the floor
    # and signal best-and-final. Next round the buyer must clear floor or we walk.
    if not buyer_within_floor:
        counter = floor_price
        # Defensive: if a stale previous_offer somehow equals/sits at floor already,
        # WALKAWAY rather than emit an illegal counter the guard would reject.
        if previous_offer is not None and counter >= previous_offer - _PRICE_EPSILON:
            return {
                "ok": True,
                "response_type": "WALKAWAY",
                "walkaway_reason": "PRICE_GAP_TOO_LARGE",
                "buyer_proposed_price": round(buyer_price, 2),
                "is_final": False,
                "reason": "floor_already_quoted_buyer_still_low",
            }
        return {
            "ok": True,
            "response_type": "COUNTER_OFFER",
            "vendor_unit_price": round(counter, 2),
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": True,
            "reason": "buyer_below_floor_counter_at_floor_final",
        }

    # Rule 9: standard linear counter at vendor_target, clamped strictly between
    # buyer_price and previous_offer so the send_response guards never fire.
    counter = vendor_target
    if previous_offer is not None and counter >= previous_offer - _PRICE_EPSILON:
        # Curve produced a non-concession. Force a step down from previous_offer.
        counter = round(max(previous_offer - _PRICE_EPSILON * 2, floor_price), 2)
    if counter <= buyer_price + _PRICE_EPSILON:
        # Counter would be at/below buyer's bid -> just accept the buyer's price
        # (already gated above by Rule 7's band check, but cover the edge).
        return {
            "ok": True,
            "response_type": "ACCEPT",
            "vendor_unit_price": round(buyer_price, 2),
            "buyer_proposed_price": round(buyer_price, 2),
            "is_final": False,
            "reason": "counter_would_be_below_buyer_bid",
        }

    is_final = round_n >= MAX_NEGOTIATION_ROUNDS - 1
    return {
        "ok": True,
        "response_type": "COUNTER_OFFER",
        "vendor_unit_price": round(counter, 2),
        "buyer_proposed_price": round(buyer_price, 2),
        "is_final": is_final,
        "reason": "linear_target_counter",
    }


# ── send_response ────────────────────────────────────────────────────────────


def send_response(
    response_type: Literal["ACCEPT", "COUNTER_OFFER", "WALKAWAY"],
    *,
    vendor_unit_price: float | None = None,
    buyer_proposed_price: float | None = None,
    is_final: bool = False,
    walkaway_reason: str = "MAX_ROUNDS_REACHED",
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Build the A2A envelope for the response type the decision tool chose.

    Hard guards (in addition to ``decide_response`` doing the math):
      - ``floor_price_violation`` — vendor_unit_price < last_selling_price
      - ``counter_above_previous_offer`` — COUNTER_OFFER >= LATEST_OFFER_PRICE_KEY
      - ``counter_below_buyer_price`` — COUNTER_OFFER <= buyer_proposed_price
      - ``max_rounds_reached`` — COUNTER_OFFER on/after MAX rounds
      - ``post_is_final_counter_rejected`` — COUNTER_OFFER after is_final was latched

    Returns ``{"ok": True, ...}`` on success (envelope queued for A2A delivery
    via callback), or ``{"ok": False, "error": ..., "hint": ...}`` on a guard hit.
    """
    vendor_id: str = tool_context.state.get(VENDOR_ID_KEY) or ""
    rfq_id: str = tool_context.state.get(RFQ_ID_KEY) or ""
    product_state: dict[str, Any] = dict(tool_context.state.get(PRODUCT_KEY) or {})

    if not vendor_id:
        return {"ok": False, "error": "vendor_id not found in session state"}
    if not rfq_id:
        return {"ok": False, "error": "rfq_id not found in session state"}

    product_id: str = product_state.get("id") or ""
    if not product_id:
        return {"ok": False, "error": "product.id missing — ensure quote agent ran first"}

    if response_type in ("ACCEPT", "COUNTER_OFFER") and vendor_unit_price is None:
        return {"ok": False, "error": f"vendor_unit_price is required for {response_type}"}

    # Mirror the buyer's round number from the incoming envelope so both sides
    # use the same round value for the same exchange turn.
    request_body = dict(tool_context.state.get("temp:request_body") or {})
    incoming_round = request_body.get("round")
    negotiation_round = int(
        incoming_round if incoming_round is not None
        else tool_context.state.get(ROUND_KEY) or 0
    )

    listed_unit_price = float(product_state.get("listed_unit_price") or 0)
    vendor_is_final = bool(tool_context.state.get(VENDOR_IS_FINAL_KEY))

    # Floor guard: vendor_unit_price must be >= last_selling_price for any priced move.
    if response_type in ("ACCEPT", "COUNTER_OFFER") and listed_unit_price > 0:
        floor_price = _to_float(tool_context.state.get(LAST_SELLING_PRICE_KEY))
        if floor_price is None:
            floor_price = round(listed_unit_price * 0.90, 2)
        if float(vendor_unit_price) < float(floor_price) - _PRICE_EPSILON:
            return {
                "ok": False,
                "error": "floor_price_violation",
                "vendor_unit_price": float(vendor_unit_price),
                "floor_price": float(floor_price),
                "hint": (
                    "vendor_unit_price is below the negotiation floor — counter at or "
                    "above floor_price, or WALKAWAY instead"
                ),
            }

    # Counter guards: only fire for COUNTER_OFFER.
    if response_type == "COUNTER_OFFER":
        previous_offer = _to_float(tool_context.state.get(LATEST_OFFER_PRICE_KEY))
        if previous_offer is not None and float(vendor_unit_price) >= float(previous_offer) - _PRICE_EPSILON:
            return {
                "ok": False,
                "error": "counter_above_previous_offer",
                "vendor_unit_price": float(vendor_unit_price),
                "previous_offer": float(previous_offer),
                "hint": (
                    "counter must be strictly below the vendor's previous offer — "
                    "concede or send ACCEPT"
                ),
            }
        if buyer_proposed_price is not None and float(vendor_unit_price) <= float(buyer_proposed_price) + _PRICE_EPSILON:
            return {
                "ok": False,
                "error": "counter_below_buyer_price",
                "vendor_unit_price": float(vendor_unit_price),
                "buyer_proposed_price": float(buyer_proposed_price),
                "hint": (
                    "counter must be strictly above buyer's proposed price — "
                    "send ACCEPT at buyer's price instead"
                ),
            }

    if response_type == "COUNTER_OFFER" and negotiation_round >= MAX_NEGOTIATION_ROUNDS:
        return {
            "ok": False,
            "error": "max_rounds_reached",
            "negotiation_round": negotiation_round,
            "max_rounds": MAX_NEGOTIATION_ROUNDS,
            "hint": "respond with ACCEPT or WALKAWAY; further counters are not allowed",
        }

    if response_type == "COUNTER_OFFER" and vendor_is_final:
        return {
            "ok": False,
            "error": "post_is_final_counter_rejected",
            "hint": (
                "a prior vendor counter was marked is_final=True; respond with "
                "ACCEPT or WALKAWAY"
            ),
        }

    builder = A2AMessageBuilder(
        rfq_id=rfq_id,
        vendor_id=vendor_id,
        product_id=product_id,
        sku=product_state.get("sku") or "",
        quantity=int(product_state.get("quantity") or 1),
        unit=product_state.get("unit") or "",
        currency=product_state.get("currency") or "USD",
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )

    if response_type == "ACCEPT":
        envelope = builder.get_accept_payload(
            unit_price=vendor_unit_price,
            negotiation_round=negotiation_round,
        )
    elif response_type == "COUNTER_OFFER":
        envelope = builder.get_counter_offer_payload(
            unit_price=vendor_unit_price,
            negotiation_round=negotiation_round,
            is_final=is_final,
        )
    elif response_type == "WALKAWAY":
        latest_offer = tool_context.state.get(LATEST_OFFER_PRICE_KEY)
        envelope = builder.get_walkaway_payload(
            walkaway_reason=walkaway_reason,
            negotiation_round=negotiation_round,
            last_unit_price=latest_offer,
        )
    else:
        return {"ok": False, "error": f"unknown response_type: {response_type!r}"}

    if buyer_proposed_price is not None:
        tool_context.state[LATEST_BUYER_PRICE_KEY] = buyer_proposed_price
    if vendor_unit_price is not None:
        tool_context.state[LATEST_OFFER_PRICE_KEY] = vendor_unit_price

    tool_context.state["temp:response_body"] = envelope

    return {
        "ok": True,
        "message_type": envelope.get("message_type"),
        "message_id": envelope.get("message_id"),
    }


# ── legacy compatibility ────────────────────────────────────────────────────


def get_negotiation_context(tool_context: ToolContext) -> dict[str, Any]:
    """Legacy read-only context (kept for tooling that introspects state).

    The decision logic lives in ``decide_response`` now; this only exposes
    state values for debugging.
    """
    product_state = dict(tool_context.state.get(PRODUCT_KEY) or {})
    listed_unit_price = float(product_state.get("listed_unit_price") or 0)
    if listed_unit_price <= 0:
        return {
            "ok": False,
            "error": "listed_unit_price is 0 in state — ensure the quote agent ran first.",
        }
    return {
        "ok": True,
        "last_selling_price": tool_context.state.get(LAST_SELLING_PRICE_KEY),
        "opening_price": tool_context.state.get(OPENING_PRICE_KEY),
        "listed_unit_price": listed_unit_price,
        "currency": product_state.get("currency") or "USD",
        "negotiation_round": int(tool_context.state.get(ROUND_KEY) or 0),
        "max_rounds": MAX_NEGOTIATION_ROUNDS,
        "latest_offer_price": tool_context.state.get(LATEST_OFFER_PRICE_KEY),
        "latest_buyer_price": tool_context.state.get(LATEST_BUYER_PRICE_KEY),
        "vendor_is_final": bool(tool_context.state.get(VENDOR_IS_FINAL_KEY)),
    }
