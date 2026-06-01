"""Product catalog queries for the UI picker."""

from __future__ import annotations

from db.collections.product import Product
from db.firestore.repositories.products import ProductRepository

_DESCRIPTION_MAX_LEN = 240


def filter_products(products: list[Product], q: str, *, limit: int) -> list[Product]:
    """Case-insensitive match on name, brand, or id; sort by name."""
    sorted_products = sorted(products, key=lambda p: p.name.lower())
    needle = q.strip().lower()
    if not needle:
        return sorted_products[:limit]
    matched = [
        p
        for p in sorted_products
        if needle in p.name.lower()
        or needle in p.brand.lower()
        or needle in p.id.lower()
    ]
    return matched[:limit]


async def search_active_products(
    repo: ProductRepository,
    *,
    q: str = "",
    limit: int = 20,
    scan_limit: int = 100,
) -> list[Product]:
    products = await repo.list_active(limit=scan_limit)
    return filter_products(products, q, limit=limit)


def truncate_description(text: str, *, max_len: int = _DESCRIPTION_MAX_LEN) -> str:
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."
