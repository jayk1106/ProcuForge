from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from db.collections.vendor_org_relation import VendorOrgRelation
from db.firestore.client import get_firestore_client
from db.firestore.repositories.vendor_org_relations import VendorOrgRelationRepository
from db.firestore.repositories.vendor_products import VendorProductRepository
from procu_forge_vendor.pricing import quantity_tier_discount_fraction, quote_valid_until
from procu_forge_vendor.state_keys import (
    BUYER_ORG_ID_KEY,
    LAST_SELLING_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    OPENING_PRICE_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    VENDOR_ID_KEY,
    VENDOR_RELATION_KEY,
)

_LOG = logging.getLogger(__name__)

# Default historical discount when no vendorOrgRelations row exists. Matches the
# buyer-side default for a new vendor (procu_forge_buyer/subagents/negotiator/tools.py).
_DEFAULT_AVG_DISCOUNT_PCT = 8.0

# Pp the opening quote sits above the floor's discount line. Concrete example:
# avg_disc=10 -> floor at listed*(1-0.10), opening at listed*(1-0.05).
_OPENING_BUFFER_PCT = 5.0

# Loyalty bump cap (extra pp) granted only to preferred vendors with strong relationships.
_MAX_LOYALTY_EXTRA_PCT = 2.0


def _compute_anchors(
    listed_unit_price: float,
    quantity: int,
    relation: VendorOrgRelation | None,
) -> dict[str, Any]:
    """Derive floor + opening + cached relation summary for this RFQ.

    Mirror of the buyer's _decide_next_move discount math
    (procu_forge_buyer/subagents/negotiator/tools.py): both sides read the
    same vendorOrgRelations row and produce symmetric anchors.
    """
    avg_disc: float = _DEFAULT_AVG_DISCOUNT_PCT
    rel_strength: float | None = None
    preferred: bool = False

    if relation is not None:
        pricing_insights = relation.pricing_insights
        if pricing_insights and pricing_insights.average_discount_percent is not None:
            avg_disc = float(pricing_insights.average_discount_percent)
        rel_strength = relation.relationship_strength
        preferred = bool(relation.preferred_vendor)

    # Loyalty bump: preferred + strong relationship earns up to 2 pp extra concession.
    # At strength <= 7 it's 0; at strength 10 it fully applies.
    loyalty_extra = 0.0
    if preferred and rel_strength is not None and rel_strength > 7:
        loyalty_extra = min(_MAX_LOYALTY_EXTRA_PCT, (float(rel_strength) - 7) / 3 * _MAX_LOYALTY_EXTRA_PCT)

    qty_tier_pct = quantity_tier_discount_fraction(quantity) * 100.0

    # Floor (hard): historical mean + loyalty + tier off catalog.
    floor_disc = avg_disc + loyalty_extra + qty_tier_pct
    last_selling_price = round(listed_unit_price * (1 - floor_disc / 100.0), 2)

    # Opening: above the historical mean to leave concession room.
    # Tier discount still applies (the buyer's quantity earns it regardless of
    # how aggressive the opener is).
    opening_disc = max(0.0, avg_disc - _OPENING_BUFFER_PCT) + qty_tier_pct
    opening_price = round(listed_unit_price * (1 - opening_disc / 100.0), 2)

    # Defensive: never let opening sink below floor (e.g. tiny avg_disc < buffer).
    if opening_price < last_selling_price:
        opening_price = last_selling_price

    summary = {
        "avg_discount_pct": avg_disc,
        "relationship_strength": rel_strength,
        "preferred_vendor": preferred,
        "loyalty_extra_pct": round(loyalty_extra, 4),
        "qty_tier_pct": qty_tier_pct,
        "relation_present": relation is not None,
    }

    return {
        "last_selling_price": last_selling_price,
        "opening_price": opening_price,
        "relation_summary": summary,
    }


async def quote_product(tool_context: ToolContext) -> dict[str, Any]:
    """Fetch vendor product + buyer-relationship context and return a QUOTE envelope.

    All inputs are read from session state seeded by the incoming RFQ:
      - state["vendor_id"]         -> which vendor to look up
      - state["buyer_org_id"]      -> buyer's organization for relation lookup
      - state["rfq_id"]            -> envelope thread identifier
      - state["product"]["id"]     -> product to quote
      - state["product"]["quantity"] -> requested units
      - state["product"]["currency"] -> preferred currency (fallback to DB record)

    Returns ``{"ok": True, ...}`` on success (envelope queued for A2A delivery via
    callback), or ``{"ok": False, "error": ...}`` on failure.
    """
    vendor_id: str = tool_context.state.get(VENDOR_ID_KEY) or ""
    buyer_org_id: str = tool_context.state.get(BUYER_ORG_ID_KEY) or ""
    rfq_id: str = tool_context.state.get(RFQ_ID_KEY) or ""
    product_state: dict[str, Any] = dict(tool_context.state.get(PRODUCT_KEY) or {})

    if not vendor_id:
        return {"ok": False, "error": "vendor_id not found in session state"}
    if not rfq_id:
        return {"ok": False, "error": "rfq_id not found in session state"}

    product_id: str = product_state.get("id") or ""
    quantity: int = int(product_state.get("quantity") or 1)
    currency: str = product_state.get("currency") or "USD"

    if not product_id:
        return {"ok": False, "error": "product.id not found in session state"}

    client = get_firestore_client()
    repo = VendorProductRepository(client)
    vp = await repo.get_by_product_and_vendor(product_id, vendor_id)

    if vp is None:
        return {
            "ok": False,
            "error": (
                f"No active vendor-product record found: "
                f"product_id={product_id!r} vendor_id={vendor_id!r}"
            ),
        }

    # Pull the buyer<->vendor relation; missing buyer_org_id (or no row) -> defaults.
    relation: VendorOrgRelation | None = None
    if buyer_org_id:
        relations_repo = VendorOrgRelationRepository(client)
        relations = await relations_repo.list_active_for_org_by_vendor_ids(
            buyer_org_id, [vendor_id]
        )
        relation = relations.get(vendor_id)

    anchors = _compute_anchors(vp.pricing.unit_price, quantity, relation)

    resolved_currency = vp.pricing.currency or currency
    product_state.update(
        {
            "id": product_id,
            "sku": vp.vendor_sku,
            "currency": resolved_currency,
            "unit": vp.unit,
            "listed_unit_price": vp.pricing.unit_price,
            "quantity": quantity,
            "lead_time_days": vp.lead_time_days,
            "availability_status": vp.availability_status,
            "minimum_order_qty": vp.pricing.minimum_order_qty,
        }
    )
    tool_context.state[PRODUCT_KEY] = product_state

    opening_price = anchors["opening_price"]
    tool_context.state[OPENING_PRICE_KEY] = opening_price
    tool_context.state[LAST_SELLING_PRICE_KEY] = anchors["last_selling_price"]
    tool_context.state[VENDOR_RELATION_KEY] = anchors["relation_summary"]
    tool_context.state[LATEST_OFFER_PRICE_KEY] = opening_price

    _LOG.info(
        "vendor_quote_anchors  rfq_id=%s vendor_id=%s buyer_org_id=%s "
        "listed=%.2f opening=%.2f floor=%.2f relation_present=%s",
        rfq_id,
        vendor_id,
        buyer_org_id or "<new>",
        vp.pricing.unit_price,
        opening_price,
        anchors["last_selling_price"],
        anchors["relation_summary"]["relation_present"],
    )

    builder = A2AMessageBuilder(
        rfq_id=rfq_id,
        vendor_id=vendor_id,
        product_id=product_id,
        sku=vp.vendor_sku,
        quantity=quantity,
        unit=vp.unit,
        currency=resolved_currency,
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )

    envelope = builder.get_quote_payload(
        unit_price=opening_price,
        negotiation_round=0,
        response_deadline=quote_valid_until(),
    )

    tool_context.state["temp:response_body"] = envelope

    return {
        "ok": True,
        "message_type": envelope.get("message_type"),
        "message_id": envelope.get("message_id"),
    }
