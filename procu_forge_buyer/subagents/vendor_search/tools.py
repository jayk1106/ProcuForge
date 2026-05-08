from __future__ import annotations

from typing import Any

from db.firestore.client import get_firestore_client
from db.firestore.repositories.vendor_products import VendorProductRepository


async def search_active_vendors_for_product(product_id: str) -> list[dict[str, Any]]:
    """Return up to 3 active vendor-products that supply the given product.

    Each entry includes vendorId, vendorSku, pricing, leadTimeDays,
    contracted flag and availabilityStatus so downstream agents
    (negotiator, decision) have enough context.
    """
    repo = VendorProductRepository(get_firestore_client())
    items = await repo.list_active_by_product(product_id, limit=3)
    return [item.model_dump(mode="json", by_alias=True) for item in items]
