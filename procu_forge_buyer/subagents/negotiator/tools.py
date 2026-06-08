from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder, MessageType
from procu_forge_buyer.a2a_client import call_vendor as _call_vendor
from procu_forge_buyer.event_hooks import publish_vendor_message, record_vendor_thread_initiated
from procu_forge_buyer.pr_status_transitions import _targeted_vendor_ids
from procu_forge_buyer.state_keys import (
    NEGOTIATION_CONFIG_KEY,
    PR_STATUS_KEY,
    REQUEST_KEY,
    VENDOR_OFFERS_KEY,
)

_LOG = logging.getLogger(__name__)

# Discount tuning constants — kept module-level so tests can monkeypatch.
_DEFAULT_EXPECTED_DISCOUNT_PCT = 8.0  # fallback when vendor_relation lacks averageDiscountPercent
_FIRST_COUNTER_EXTRA_PCT = 3.0        # round-0 counter: catalog * (1 - (expected + 3) / 100)
_COUNTER_FLOOR_EXTRA_PCT = 5.0        # later counters floored at catalog * (1 - (expected + 5) / 100)
_ACCEPT_BAND_PCT = 1.03               # vendor_price <= target * 1.03 -> accept after round 0
_VENDOR_COUNTER_SHAVE = 0.94          # default counter is vendor_price * 0.94
# Hard cap on negotiation rounds. After this many buyer rounds, WALKAWAY(MAX_ROUNDS_REACHED).
# Must stay in sync with vendor side (procu_forge_vendor/subagents/negotiation/tools.py:_MAX_ROUNDS).
_MAX_NEGOTIATION_ROUNDS = 5


# ── logging helpers ───────────────────────────────────────────────────────────

def _comm_tag(entry: Any) -> str:
    if isinstance(entry, dict):
        return (
            f"{entry.get('message_type', '?')}("
            f"r{entry.get('round', '?')}, "
            f"id={str(entry.get('message_id', ''))[:8]})"
        )
    if isinstance(entry, str):
        return f"vendor_text({len(entry)}chars)"
    return repr(entry)[:60]


def _log_before_vendor_call(
    config: dict[str, Any],
    message_type: MessageType,
    negotiation_round: int,
    payload: dict[str, Any],
) -> None:
    comms = config.get("communications") or []
    _LOG.info(
        "a2a_call_start  rfq_id=%s vendor_id=%s round=%d message_type=%s "
        "prior_comms=%d prior=[%s]",
        config.get("rfq_id"),
        config.get("vendor_id"),
        negotiation_round,
        str(message_type),
        len(comms),
        ", ".join(_comm_tag(c) for c in comms),
    )
    _LOG.debug(
        "a2a_payload  rfq_id=%s payload=%s",
        config.get("rfq_id"),
        json.dumps(payload, default=str),
    )


def _log_after_vendor_call(
    config: dict[str, Any],
    negotiation_round: int,
    reply: str,
) -> None:
    _LOG.info(
        "a2a_call_end  rfq_id=%s vendor_id=%s round=%d reply_chars=%d",
        config.get("rfq_id"),
        config.get("vendor_id"),
        negotiation_round,
        len(reply),
    )
    _LOG.debug(
        "a2a_reply  rfq_id=%s reply=%s",
        config.get("rfq_id"),
        reply[:2000],
    )


# ── state / config helpers ────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_quantity(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _get(d: dict[str, Any], *keys: str) -> Any:
    """Return the first non-None value from ``d`` for any of ``keys``."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


_BUYER_AGENT_NAMES = {"buyer_negotiator", "buyer_agent"}


def _coerce_dict(item: Any) -> dict[str, Any] | None:
    """Return ``item`` as a dict, decoding JSON strings when possible."""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_last_vendor_message(comms: list[Any]) -> dict[str, Any] | None:
    """Walk ``comms`` newest-first; return the most recent vendor-originated envelope."""
    for entry in reversed(comms or []):
        env = _coerce_dict(entry)
        if env is None:
            continue
        from_agent = str(env.get("from_agent") or "")
        if from_agent in _BUYER_AGENT_NAMES:
            continue
        return env
    return None


def _is_deadline_past(deadline: Any) -> bool:
    """True only when ``deadline`` parses to a UTC datetime strictly in the past."""
    if not isinstance(deadline, str) or not deadline.strip():
        return False
    raw = deadline.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < datetime.now(timezone.utc)


def _vendor_envelope_price(env: dict[str, Any]) -> float | None:
    """Pull the unit price from a vendor envelope (handles WALKAWAY's alt key)."""
    payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
    msg_type = str(env.get("message_type") or "")
    if msg_type == MessageType.WALKAWAY.value:
        return _to_float(payload.get("last_unit_price"))
    return _to_float(payload.get("unit_price"))


def _decide_next_move(
    vendor_state: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Compute the buyer's next message for a single vendor.

    Returns a dict shaped exactly like ``negotiate_with_vendor``'s
    ``communication_data`` argument so the agent can pass it through verbatim:
    ``{vendor_id, message_type, price?, walkaway_reason?, reason}``.

    Rule order (first match wins — order is load-bearing):

    1. last vendor msg is WALKAWAY -> mirror with WALKAWAY(VENDOR_REJECTED)
    2. last vendor msg is ACCEPT -> ACCEPT if within budget; else WALKAWAY(PRICE_GAP_TOO_LARGE)
    3. currency mismatch vs request -> WALKAWAY(PRICE_GAP_TOO_LARGE)
    4. response_deadline parseable and past -> WALKAWAY(QUOTE_EXPIRED)
    5. vendor is_final=True -> ACCEPT if within budget; else WALKAWAY(PRICE_GAP_TOO_LARGE)
    6. round >= _MAX_NEGOTIATION_ROUNDS -> WALKAWAY(MAX_ROUNDS_REACHED) (only when vendor isn't final)
    7. round == 0 AND vendor_price > target -> COUNTER (force first counter even on generous budgets)
    8. vendor_price within ACCEPT band of target AND within budget -> ACCEPT
    9. else COUNTER, floored at counter_floor and capped at budget_per_unit

    Invariant after these rules: the buyer never sends ACCEPT or COUNTER above
    budget_per_unit (when one is configured).
    """
    vendor_id = vendor_state["vendor_id"]
    comms = vendor_state.get("communications") or []
    last = _extract_last_vendor_message(comms)

    target_price = _to_float(vendor_state.get("target_price")) or 0.0
    budget_per_unit = _to_float(vendor_state.get("budget_per_unit"))
    catalog_price = _to_float(vendor_state.get("catalog_price")) or 0.0
    expected_disc = _to_float(vendor_state.get("expected_discount_pct")) or _DEFAULT_EXPECTED_DISCOUNT_PCT
    rel_strength = _to_float(vendor_state.get("relationship_strength"))
    cur_round = vendor_state.get("round")

    # Strong relationships get a gentler counter: we shave up to 2 percentage
    # points off the extra-discount ask. At strength 10 the softener fully
    # applies; at strength <=3 there is none.
    softener = 0.0
    if rel_strength is not None and rel_strength > 3:
        softener = min(2.0, (rel_strength - 3) / 7 * 2)
    first_counter_extra = max(0.5, _FIRST_COUNTER_EXTRA_PCT - softener)
    floor_extra = max(first_counter_extra + 1.0, _COUNTER_FLOOR_EXTRA_PCT - softener)

    # No vendor reply yet -> open the thread with an RFQ.
    if last is None:
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.RFQ.value,
            "reason": "open_thread",
        }

    last_payload = last.get("payload") if isinstance(last.get("payload"), dict) else {}
    last_type = str(last.get("message_type") or "")
    vendor_price = _vendor_envelope_price(last)
    is_final = bool(last_payload.get("is_final"))

    # 1. Vendor walked away.
    if last_type == MessageType.WALKAWAY.value:
        out: dict[str, Any] = {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "VENDOR_REJECTED",
            "reason": "vendor_walkaway",
        }
        if vendor_price is not None:
            out["price"] = vendor_price
        return out

    # 2. Vendor accepted (rare — vendor usually accepts only after buyer COUNTER).
    # Mirror only when within budget; otherwise walk away rather than auto-confirm
    # an above-budget deal the vendor unilaterally locked in.
    if last_type == MessageType.ACCEPT.value and vendor_price is not None:
        if budget_per_unit is None or vendor_price <= budget_per_unit:
            return {
                "vendor_id": vendor_id,
                "message_type": MessageType.ACCEPT.value,
                "price": vendor_price,
                "reason": "vendor_accepted",
            }
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "price": vendor_price,
            "reason": "vendor_accepted_above_budget",
        }

    # 3. Currency drift — vendor switched away from the request currency.
    req_currency = str(request.get("currency") or "").upper()
    last_currency = str(last_payload.get("currency") or "").upper()
    if req_currency and last_currency and req_currency != last_currency:
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "reason": f"currency_mismatch ({last_currency} != {req_currency})",
        }

    # 4. Quote expired.
    if _is_deadline_past(last_payload.get("response_deadline")):
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "QUOTE_EXPIRED",
            "reason": "response_deadline_past",
        }

    # 5. Vendor declared best-and-final. ACCEPT if within budget; otherwise
    # WALKAWAY — the vendor has signalled they won't move, so further counters
    # are wasted rounds.
    if is_final and vendor_price is not None:
        if budget_per_unit is None or vendor_price <= budget_per_unit:
            return {
                "vendor_id": vendor_id,
                "message_type": MessageType.ACCEPT.value,
                "price": vendor_price,
                "reason": "is_final_within_budget",
            }
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "price": vendor_price,
            "reason": "is_final_above_budget",
        }

    # 6. Rounds exhausted.
    last_round = int(cur_round) if isinstance(cur_round, int) else 0
    if last_round >= _MAX_NEGOTIATION_ROUNDS:
        out = {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "MAX_ROUNDS_REACHED",
            "reason": f"round_{last_round}_exhausted",
        }
        if vendor_price is not None:
            out["price"] = vendor_price
        return out

    if vendor_price is None:
        # Defensive: missing price but vendor neither walked away nor accepted.
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.WALKAWAY.value,
            "walkaway_reason": "PRICE_GAP_TOO_LARGE",
            "reason": "vendor_envelope_missing_price",
        }

    counter_floor = round(catalog_price * (1 - (expected_disc + floor_extra) / 100), 2)

    # 7. First buyer response after the opening QUOTE — push BELOW the vendor's
    # average discount so we leave room for the vendor to counter back up to our
    # target. Cap at counter_floor so we don't insult the vendor with a low-ball.
    if last_round == 0:
        aggressive = round(catalog_price * (1 - (expected_disc + first_counter_extra) / 100), 2)
        counter = max(aggressive, counter_floor)
        # Respect the per-unit budget cap if defined.
        if budget_per_unit is not None and counter > budget_per_unit:
            counter = budget_per_unit
        # Must be strictly below the vendor's quote.
        if counter >= vendor_price:
            counter = round(vendor_price * _VENDOR_COUNTER_SHAVE, 2)
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.COUNTER_OFFER.value,
            "price": round(counter, 2),
            "reason": "round0_below_avg_discount",
        }

    # 8. Close enough after at least one round of negotiation — accept the
    # vendor's best offer rather than risk a walkaway over pennies. Band-accept
    # is gated on budget: the band can mathematically exceed budget_per_unit
    # when target ≈ budget, so re-check explicitly.
    within_band = vendor_price <= target_price * _ACCEPT_BAND_PCT
    within_budget = budget_per_unit is None or vendor_price <= budget_per_unit
    if within_band and within_budget:
        return {
            "vendor_id": vendor_id,
            "message_type": MessageType.ACCEPT.value,
            "price": vendor_price,
            "reason": "within_accept_band",
        }

    # 9. Standard counter — tighten toward target without pushing below the
    # vendor's plausible floor, and never above the budget cap (a vendor ACCEPT
    # of an above-budget counter would silently blow the budget).
    counter = max(target_price, round(vendor_price * _VENDOR_COUNTER_SHAVE, 2), counter_floor)
    counter = round(min(counter, vendor_price), 2)
    if budget_per_unit is not None and counter > budget_per_unit:
        counter = round(budget_per_unit, 2)
    return {
        "vendor_id": vendor_id,
        "message_type": MessageType.COUNTER_OFFER.value,
        "price": counter,
        "reason": "standard_counter",
    }


def build_negotiation_progress(state: dict[str, Any]) -> dict[str, Any]:
    """Serializable per-turn snapshot embedded in the negotiator's instruction.

    Mirrors :func:`build_purchase_progress`: the LLM reads the snapshot and
    calls ``negotiate_with_vendor(communication_data=vendor.recommended_action)``
    verbatim instead of recomputing the move itself.
    """
    targeted = _targeted_vendor_ids(state)
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}

    vendors: list[dict[str, Any]] = []
    for vendor_id in targeted:
        config = nego.get(vendor_id)
        config = config if isinstance(config, dict) else {}
        done = bool(config.get("done"))

        last = _extract_last_vendor_message(config.get("communications") or [])
        last_payload = (
            last.get("payload") if last and isinstance(last.get("payload"), dict) else {}
        )

        recommendation: dict[str, Any] | None = None
        if not done:
            # Synthesize the minimum config _decide_next_move needs when the
            # vendor thread hasn't been opened yet (no rfq_id, no comms).
            seed = (
                config
                if config.get("rfq_id")
                else {
                    "vendor_id": vendor_id,
                    "round": None,
                    "communications": [],
                    "target_price": None,
                    "budget_per_unit": None,
                    "catalog_price": None,
                    "expected_discount_pct": None,
                }
            )
            recommendation = _decide_next_move(seed, request)

        vendors.append(
            {
                "vendor_id": vendor_id,
                "done": done,
                "round": config.get("round"),
                "target_price": config.get("target_price"),
                "budget_per_unit": config.get("budget_per_unit"),
                "expected_discount_pct": config.get("expected_discount_pct"),
                "relationship_strength": config.get("relationship_strength"),
                "preferred_vendor": config.get("preferred_vendor"),
                "catalog_price": config.get("catalog_price"),
                "last_message_type": (last or {}).get("message_type"),
                "last_vendor_price": _vendor_envelope_price(last) if last else None,
                "last_is_final": bool(last_payload.get("is_final")) if last else False,
                "last_currency": last_payload.get("currency") if last else None,
                "recommended_action": recommendation,
            }
        )

    return {
        "pr_status": state.get(PR_STATUS_KEY),
        "currency": request.get("currency"),
        "quantity": request.get("quantity"),
        "budget_ceiling": request.get("budget_ceiling"),
        "targeted_vendor_ids": targeted,
        "all_done": bool(targeted) and all(v["done"] for v in vendors),
        "vendors": vendors,
    }


def _init_vendor_config(state: dict[str, Any], vendor_id: str) -> dict[str, Any] | str:
    """Build a fresh per-vendor negotiation config from ``vendor_offers``.

    ``target_price`` is the per-unit price the buyer will try to land. It is the
    tighter of ``budget_ceiling / quantity`` (the cap that keeps total spend in
    bounds) and ``catalog * (1 - expected_discount_pct/100)`` (the relationship-
    aware target that ensures we always have negotiation room — otherwise a
    generous budget would let the buyer ACCEPT the first quote on round 0).
    """
    block = state.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return "vendor_offers is missing or invalid in session state"

    product_id = _get(block, "productId", "product_id")
    offers = block.get("offers")
    if not product_id or not isinstance(offers, list):
        return "vendor_offers.productId or offers is invalid"

    offer = next(
        (
            o
            for o in offers
            if isinstance(o, dict)
            and str(_get(o, "vendorId", "vendor_id") or "").strip() == vendor_id
        ),
        None,
    )
    if offer is None:
        return f"no offer for vendor_id={vendor_id!r}"

    unit_price = _to_float(_get(offer, "unitPrice", "unit_price"))
    if unit_price is None:
        return "offer has no valid unit price"

    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    quantity = _to_quantity(request.get("quantity"))

    vendor_relation = offer.get("vendorRelation") or offer.get("vendor_relation") or {}
    expected_discount_pct = _to_float(
        _get(vendor_relation, "averageDiscountPercent", "average_discount_percent")
    )
    if expected_discount_pct is None or expected_discount_pct < 0:
        expected_discount_pct = _DEFAULT_EXPECTED_DISCOUNT_PCT
    relationship_strength = _to_float(
        _get(vendor_relation, "relationshipStrength", "relationship_strength")
    )
    preferred_vendor = bool(_get(vendor_relation, "preferredVendor", "preferred_vendor"))

    budget_ceiling = _to_float(request.get("budget_ceiling"))
    budget_per_unit = (
        round(budget_ceiling / quantity, 2)
        if budget_ceiling is not None and quantity > 0
        else None
    )

    discount_target = round(unit_price * (1 - expected_discount_pct / 100), 2)
    target_price = (
        round(min(budget_per_unit, discount_target), 2)
        if budget_per_unit is not None
        else discount_target
    )

    return {
        "target_price": target_price,
        "budget_per_unit": budget_per_unit,
        "expected_discount_pct": expected_discount_pct,
        "relationship_strength": relationship_strength,
        "preferred_vendor": preferred_vendor,
        "catalog_price": unit_price,
        "vendor_id": vendor_id,
        "rfq_id": str(uuid4()),
        "round": None,
        "product": {
            "id": str(product_id),
            "sku": str(_get(offer, "vendorSku", "vendor_sku") or ""),
            "currency": str(offer.get("currency") or ""),
            "unit": str(offer.get("unit") or ""),
            "price": unit_price,
            "quantity": quantity,
        },
        "communications": [],
    }


# ── broadcast helpers ─────────────────────────────────────────────────────────

def _broadcast_buyer_state(workflow_id: str, *, reason: str) -> None:
    """Push the latest workflow DTO to the flow channel. Fire-and-forget."""
    try:
        from api.services.workflow_query import build_workflow_detail
        from api.ws import broadcast_state

        broadcast_state(
            workflow_id,
            lambda wid=workflow_id: build_workflow_detail(wid),
            reason=reason,
            workflow_id=workflow_id,
        )
    except Exception:
        _LOG.exception(
            "negotiator.tools.broadcast_buyer_failed workflow_id=%s reason=%s",
            workflow_id,
            reason,
        )


def _broadcast_vendor_thread(workflow_id: str, rfq_id: str) -> None:
    """Push the latest vendor-thread DTO to the vt:{rfq_id} channel. Fire-and-forget."""
    try:
        from api.services.vendor_thread_query import build_vendor_convo
        from api.ws import broadcast_state, vendor_thread_channel

        broadcast_state(
            vendor_thread_channel(rfq_id),
            lambda rid=rfq_id: build_vendor_convo(rid),
            reason="negotiation_reply",
            workflow_id=workflow_id,
            vendor_thread_id=rfq_id,
        )
    except Exception:
        _LOG.exception(
            "negotiator.tools.broadcast_vendor_thread_failed rfq_id=%s",
            rfq_id,
        )


# ── tool ──────────────────────────────────────────────────────────────────────

async def negotiate_with_vendor(
    communication_data: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Negotiate with a single vendor over A2A.

    Required: ``vendor_id``, ``message_type`` (RFQ | COUNTER_OFFER | ACCEPT | WALKAWAY).
    Conditional: ``price`` for COUNTER_OFFER/ACCEPT, ``walkaway_reason`` for WALKAWAY.
    """
    vendor_id = str(communication_data.get("vendor_id") or "").strip()
    if not vendor_id:
        return {"ok": False, "error": "vendor_id must be a non-empty string"}

    try:
        message_type = MessageType(str(communication_data.get("message_type") or "").strip())
    except ValueError:
        return {
            "ok": False,
            "error": "message_type must be one of RFQ, COUNTER_OFFER, ACCEPT, WALKAWAY",
        }

    price = communication_data.get("price")
    walkaway_reason = communication_data.get("walkaway_reason")

    if message_type == MessageType.WALKAWAY and not (
        isinstance(walkaway_reason, str) and walkaway_reason.strip()
    ):
        return {"ok": False, "error": "walkaway_reason is required for WALKAWAY"}

    if message_type in (MessageType.COUNTER_OFFER, MessageType.ACCEPT) and _to_float(price) is None:
        return {"ok": False, "error": f"numeric price is required for {message_type.value}"}

    state = tool_context.state
    # Copy the top-level negotiation dict so mutations are detected by ADK state.
    nego: dict[str, Any] = dict(state.get(NEGOTIATION_CONFIG_KEY) or {})

    config = nego.get(vendor_id)
    if isinstance(config, dict) and config.get("done"):
        # Vendor thread already closed by an earlier ACCEPT/WALKAWAY. Refuse to
        # reopen it so transition_after_negotiation can converge on
        # NEGOTIATION_COMPLETED instead of looping forever.
        _LOG.info(
            "a2a_call_skip_already_done  vendor_id=%s rfq_id=%s round=%s",
            vendor_id,
            config.get("rfq_id"),
            config.get("round"),
        )
        return {
            "ok": True,
            "rfq_id": config.get("rfq_id"),
            "vendor_id": vendor_id,
            "round": config.get("round"),
            "done": True,
            "vendor_reply": None,
            "note": "already_done",
        }

    if not isinstance(config, dict) or not config.get("rfq_id"):
        result = _init_vendor_config(state, vendor_id)
        if isinstance(result, str):
            return {"ok": False, "error": result}
        config = result
        nego[vendor_id] = config
        state[NEGOTIATION_CONFIG_KEY] = nego  # write-back so ADK persists the new rfq_id

        await record_vendor_thread_initiated(
            workflow_id=tool_context.session.id,
            rfq_id=str(config["rfq_id"]),
            vendor_id=vendor_id,
            state=state,
        )

    round = config.get("round")
    if message_type == MessageType.RFQ:
        round = 0
    else:
        if round is None:
            return {"ok": False, "error": "send RFQ before other message types"}
        round = int(round) + 1

    product = config.get("product") or {}
    builder = A2AMessageBuilder(
        rfq_id=config["rfq_id"],
        vendor_id=vendor_id,
        product_id=str(product.get("id") or ""),
        sku=str(product.get("sku") or ""),
        quantity=_to_quantity(product.get("quantity")),
        unit=str(product.get("unit") or ""),
        currency=str(product.get("currency") or ""),
    )

    if message_type == MessageType.RFQ:
        communication_payload = builder.get_rfq_payload(negotiation_round=round)
    elif message_type == MessageType.COUNTER_OFFER:
        communication_payload = builder.get_counter_offer_payload(float(price), round)
    elif message_type == MessageType.ACCEPT:
        communication_payload = builder.get_accept_payload(float(price), round)
    else:
        communication_payload = builder.get_walkaway_payload(
            walkaway_reason, round, last_unit_price=_to_float(price)
        )

    _log_before_vendor_call(config, message_type, round, communication_payload)
    config["communications"].append(communication_payload)
    config["round"] = round
    # Early write-back so the outbound broadcast (next) reads the buyer state
    # with the new message already attached. Without this, the broadcast factory
    # would build a DTO from a session snapshot that's missing the outbound.
    nego[vendor_id] = config
    state[NEGOTIATION_CONFIG_KEY] = nego

    publish_vendor_message(
        workflow_id=tool_context.session.id,
        rfq_id=str(config["rfq_id"]),
        vendor_id=vendor_id,
        direction="outbound",
        message_type=str(message_type),
        round_num=round,
        payload=communication_payload,
    )

    # Outbound broadcast: push the buyer's message to the flow channel right
    # away so the negotiation card shows progress instead of going silent for
    # the duration of the A2A round-trip. Workflow channel only — the vendor's
    # session (which feeds vt:{rfq_id}) doesn't have this message yet.
    _broadcast_buyer_state(tool_context.session.id, reason="negotiation_outbound")

    reply = await _call_vendor(
        message_json=json.dumps(communication_payload),
        rfq_id=config["rfq_id"],
    )

    parsed_reply: Any = None
    try:
        parsed_reply = json.loads(reply)
        config["communications"].append(parsed_reply if isinstance(parsed_reply, dict) else reply)
    except json.JSONDecodeError:
        config["communications"].append(reply)
    if message_type in (MessageType.ACCEPT, MessageType.WALKAWAY):
        config["done"] = True
    nego[vendor_id] = config
    state[NEGOTIATION_CONFIG_KEY] = nego  # final write-back including vendor reply

    inbound_payload = parsed_reply if isinstance(parsed_reply, dict) else {"text": reply}
    publish_vendor_message(
        workflow_id=tool_context.session.id,
        rfq_id=str(config["rfq_id"]),
        vendor_id=vendor_id,
        direction="inbound",
        message_type=str(inbound_payload.get("message_type") or ""),
        round_num=round,
        payload=inbound_payload,
    )

    # Inbound broadcast: workflow channel (buyer state now has vendor reply)
    # + vendor_thread channel (vendor session now has the full round).
    _broadcast_buyer_state(tool_context.session.id, reason="negotiation_reply")
    _broadcast_vendor_thread(tool_context.session.id, str(config["rfq_id"]))

    _log_after_vendor_call(config, round, reply)

    return {
        "ok": True,
        "rfq_id": config["rfq_id"],
        "vendor_id": vendor_id,
        "round": round,
        "done": config.get("done", False),
        "vendor_reply": reply,
    }
