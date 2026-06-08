from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from db.collections.vendor_product import VendorProduct
from db.firestore.client import get_firestore_client
from db.firestore.repositories.vendor_products import VendorProductRepository

from ...pr_status import PrStatus
from ...pr_status_transitions import transition_after_vendor_discovery
from ...escalation import maybe_notify_only
from ...state_keys import VENDOR_OFFERS_KEY
from .schema import ProductVendorOffers, VendorOffer


def _offers_from_rows(items: list[VendorProduct]) -> list[VendorOffer]:
    return [
        VendorOffer(
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
        )
        for item in items
    ]


async def load_vendor_offers_for_product(tool_context: ToolContext) -> dict[str, Any]:
    """Load up to three active supplier lines for the workflow product and record them in state.

    Uses ``request.product_id``. Persists **session.state.vendor_offers** as
    ``ProductVendorOffers`` (``productId`` + ``offers`` only).
    """
    request = tool_context.state.get("request")
    if not isinstance(request, dict):
        return {
            "ok": False,
            "error": "request is missing or invalid in session state",
        }

    product_id = request.get("product_id")
    if not product_id:
        return {
            "ok": False,
            "error": "request.product_id is missing",
        }

    product_id_str = str(product_id)
    repo = VendorProductRepository(get_firestore_client())
    items = await repo.list_active_by_product(product_id_str, limit=3)
    offers = _offers_from_rows(items)

    block = ProductVendorOffers(product_id=product_id_str, offers=offers)
    payload = block.model_dump(mode="json", by_alias=True)
    tool_context.state[VENDOR_OFFERS_KEY] = payload
    transition_after_vendor_discovery(tool_context.state, offer_count=len(offers))
    if len(offers) == 0:
        maybe_notify_only(
            tool_context.state,
            source="no_vendors_discovered",
            reason="No suppliers found for product — human may onboard vendors or fix catalog data",
        )

    return {
        "ok": True,
        "productId": product_id_str,
        "offers": [o.model_dump(mode="json", by_alias=True) for o in offers],
        "offerCount": len(offers),
    }
