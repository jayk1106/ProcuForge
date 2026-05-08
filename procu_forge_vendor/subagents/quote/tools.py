from __future__ import annotations

import uuid
from typing import Any

from procu_forge_vendor.pricing import (
    lead_time_days,
    quantity_tier_discount_fraction,
    quoted_unit_price,
    quote_valid_until,
    stable_hash_int,
)


def generate_quote(product_id: str, quantity: int, currency: str = "USD") -> dict[str, Any]:
    """Issue a deterministic mock quote for an RFQ.

    Args:
        product_id: Catalog product identifier from the buyer RFQ.
        quantity: Requested units.
        currency: ISO currency code (default USD).

    Returns:
        Quote payload with quote_id, unit_price, line_total, lead_time_days, etc.
    """
    unit = quoted_unit_price(product_id, quantity)
    tier = quantity_tier_discount_fraction(quantity)
    quote_id = str(uuid.uuid4())
    return {
        "quote_id": quote_id,
        "product_id": product_id,
        "quantity": quantity,
        "currency": currency,
        "unit_price": unit,
        "line_total": round(unit * quantity, 2),
        "quantity_tier_discount": tier,
        "lead_time_days": lead_time_days(product_id),
        "valid_until": quote_valid_until(),
        "availability": "in_stock_mock",
        "notes": f"Synthetic quote; hash_seed={stable_hash_int(product_id) % 10000}",
    }
