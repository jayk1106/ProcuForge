from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import ProductRepositoryDep, get_current_admin
from api.schemas.product import ProductOptionDTO
from api.services.product_query import search_active_products

router = APIRouter(
    prefix="/products",
    tags=["products"],
    dependencies=[Depends(get_current_admin)],
)

_MAX_LIMIT = 50


@router.get(
    "",
    response_model=list[ProductOptionDTO],
    summary="Search active products for the create-request picker",
)
async def list_products(
    repo: ProductRepositoryDep,
    q: str = Query(default="", description="Filter by name, brand, or product id."),
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
) -> list[ProductOptionDTO]:
    products = await search_active_products(repo, q=q, limit=limit)
    return [ProductOptionDTO.from_product(p) for p in products]
