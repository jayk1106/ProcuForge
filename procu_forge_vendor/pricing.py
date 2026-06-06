"""Deterministic synthetic pricing for mock vendor quotes (no Firestore)."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta


def stable_hash_int(product_id: str) -> int:
    digest = hashlib.sha256(product_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def list_unit_price_before_tier(product_id: str) -> float:
    """Base list unit price before quantity-tier discount."""
    h = stable_hash_int(product_id)
    return float(100 + (h % 900))


def quantity_tier_discount_fraction(quantity: int) -> float:
    if quantity >= 50:
        return 0.10
    if quantity >= 10:
        return 0.05
    return 0.0


def quoted_unit_price(product_id: str, quantity: int) -> float:
    """Initial quoted unit price after tier discount."""
    base = list_unit_price_before_tier(product_id)
    discount = quantity_tier_discount_fraction(quantity)
    return round(base * (1.0 - discount), 2)


def floor_unit_price(product_id: str, quantity: int) -> float:
    """Minimum acceptable unit price (88% of quoted list price after tiers)."""
    return round(quoted_unit_price(product_id, quantity) * 0.88, 2)


def lead_time_days(product_id: str) -> int:
    h = stable_hash_int(product_id)
    return 5 + (h % 10)


def quote_valid_until() -> str:
    return (date.today() + timedelta(days=7)).isoformat()
