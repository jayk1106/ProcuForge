from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from google.adk.tools import ToolContext

from db.collections.vendor_org_relation import VendorOrgRelation
from db.collections.vendor_product import VendorProduct
from db.firestore.client import get_firestore_client
from db.firestore.repositories.vendor_org_relations import VendorOrgRelationRepository
from db.firestore.repositories.vendor_products import VendorProductRepository

from ...escalation import maybe_notify_only
from ...pr_status_transitions import transition_after_vendor_discovery
from ...state_keys import VENDOR_OFFERS_KEY
from .schema import ProductVendorOffers, VendorOffer, VendorRelationSummary

_CANDIDATE_POOL_SIZE = 10
_FINAL_OFFER_COUNT = 3
_ALLOWED_AVAILABILITY = {"in_stock", "limited"}


def _days_until(iso_date: str | None) -> int | None:
    """Days from today (UTC) until ``iso_date`` (YYYY-MM-DD). None if unparseable."""
    if not iso_date:
        return None
    try:
        target = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return None
    today = datetime.now(timezone.utc).date()
    return (target - today).days


def _summarize_relation(relation: VendorOrgRelation | None) -> VendorRelationSummary | None:
    if relation is None:
        return None
    metrics = relation.metrics
    pricing = relation.pricing_insights
    risk = relation.risk_insights
    return VendorRelationSummary(
        preferred_vendor=relation.preferred_vendor,
        relationship_status=relation.relationship_status,
        relationship_strength=relation.relationship_strength,
        average_delivery_delay_days=metrics.average_delivery_delay_days if metrics else None,
        quality_score=metrics.quality_score if metrics else None,
        risk_level=risk.risk_level if risk else None,
        usually_offers_discount=pricing.usually_offers_discount if pricing else None,
        average_discount_percent=pricing.average_discount_percent if pricing else None,
    )


def _build_offer(
    item: VendorProduct,
    *,
    request_currency: str,
    relation: VendorOrgRelation | None,
) -> VendorOffer:
    return VendorOffer(
        id=item.id,
        vendor_id=item.vendor_id,
        product_id=item.product_id,
        vendor_sku=item.vendor_sku,
        unit=item.unit,
        unit_price=item.pricing.unit_price,
        currency=item.pricing.currency,
        lead_time_days=item.lead_time_days,
        contracted=item.contracted,
        availability_status=item.availability_status,
        minimum_order_qty=item.pricing.minimum_order_qty,
        currency_matches_request=item.pricing.currency.upper() == request_currency.upper(),
        vendor_relation=_summarize_relation(relation),
    )


def _filter_candidates(
    items: list[VendorProduct],
    *,
    requested_quantity: int,
    days_until_required: int | None,
) -> tuple[list[VendorProduct], dict[str, int]]:
    """Apply strict drops; return survivors and per-reason drop counts."""
    counts = {"availability": 0, "moq": 0, "leadTime": 0}
    kept: list[VendorProduct] = []
    for item in items:
        if item.availability_status not in _ALLOWED_AVAILABILITY:
            counts["availability"] += 1
            continue
        if item.pricing.minimum_order_qty > requested_quantity:
            counts["moq"] += 1
            continue
        if days_until_required is not None and item.lead_time_days > days_until_required:
            counts["leadTime"] += 1
            continue
        kept.append(item)
    return kept, counts


def _rank_key(offer: VendorOffer) -> tuple[int, int, float, int, float, str]:
    """Lower is better. Hard guarantees (contracted) win over soft signals."""
    relation = offer.vendor_relation
    preferred = relation.preferred_vendor if relation else False
    strength = relation.relationship_strength if relation else None
    return (
        0 if offer.contracted else 1,
        0 if preferred else 1,
        -(strength if strength is not None else 0.0),
        offer.lead_time_days,
        offer.unit_price,
        offer.id,
    )


def _filter_summary_reason(counts: dict[str, int]) -> str:
    parts = [f"{k}={v}" for k, v in counts.items() if v > 0]
    detail = ", ".join(parts) if parts else "no_matching_candidates"
    return (
        f"All discovered vendors filtered out ({detail}). "
        "Consider relaxing required_by_date, lowering MOQ requirements, or onboarding faster suppliers."
    )


async def load_vendor_offers_for_product(tool_context: ToolContext) -> dict[str, Any]:
    """Load active supplier lines for the workflow product, filter and rank them, then record state.

    Pipeline: fetch ≤10 active vendor_products → filter (availability, MOQ, lead-time vs
    ``request.required_by_date``) → enrich with ``vendorOrgRelations`` for ``request.organization_id``
    → rank (contracted > preferred > relationship_strength > lead_time > unit_price) → take top 3.
    Persists ``session.state.vendor_offers`` as ``ProductVendorOffers`` (productId + offers).
    """
    request = tool_context.state.get("request")
    if not isinstance(request, dict):
        return {"ok": False, "error": "request is missing or invalid in session state"}

    product_id = request.get("product_id")
    if not product_id:
        return {"ok": False, "error": "request.product_id is missing"}

    organization_id = request.get("organization_id") or ""
    request_currency = str(request.get("currency") or "")
    requested_quantity = int(request.get("quantity") or 0)
    days_until_required = _days_until(request.get("required_by_date"))

    product_id_str = str(product_id)
    client = get_firestore_client()
    vp_repo = VendorProductRepository(client)
    relations_repo = VendorOrgRelationRepository(client)

    candidates = await vp_repo.list_active_by_product(product_id_str, limit=_CANDIDATE_POOL_SIZE)
    filtered, filter_counts = _filter_candidates(
        candidates,
        requested_quantity=requested_quantity,
        days_until_required=days_until_required,
    )

    relations: dict[str, VendorOrgRelation] = {}
    if filtered and organization_id:
        relations = await relations_repo.list_active_for_org_by_vendor_ids(
            organization_id, [item.vendor_id for item in filtered]
        )

    enriched = [
        _build_offer(item, request_currency=request_currency, relation=relations.get(item.vendor_id))
        for item in filtered
    ]
    enriched.sort(key=_rank_key)
    final_offers = enriched[:_FINAL_OFFER_COUNT]

    block = ProductVendorOffers(product_id=product_id_str, offers=final_offers)
    tool_context.state[VENDOR_OFFERS_KEY] = block.model_dump(mode="json", by_alias=True)
    transition_after_vendor_discovery(tool_context.state, offer_count=len(final_offers))

    if len(final_offers) == 0:
        if not candidates:
            maybe_notify_only(
                tool_context.state,
                source="no_vendors_discovered",
                reason="No suppliers found for product — human may onboard vendors or fix catalog data",
            )
        else:
            maybe_notify_only(
                tool_context.state,
                source="vendors_all_filtered",
                reason=_filter_summary_reason(filter_counts),
                recommended_action=(
                    "Review request.required_by_date and request.quantity, or onboard faster suppliers."
                ),
            )

    return {
        "ok": True,
        "productId": product_id_str,
        "candidateCount": len(candidates),
        "offerCount": len(final_offers),
        "filteredOut": filter_counts,
    }
