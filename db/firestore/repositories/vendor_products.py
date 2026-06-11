from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from db.collections.vendor_product import COLLECTION_ID, VendorProduct
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class VendorProductRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def create(self, vendor_product: VendorProduct, **write_kwargs: Any) -> None:
        def _op() -> None:
            ref = self._collection.document(vendor_product.id)
            data = model_to_firestore_dict(vendor_product, include_id_in_body=False, timestamps="create")
            ref.create(data, **write_kwargs)

        await asyncio.to_thread(_op)

    async def replace(self, vendor_product: VendorProduct) -> None:
        def _op() -> None:
            ref = self._collection.document(vendor_product.id)
            data = model_to_firestore_dict(vendor_product, include_id_in_body=False, timestamps="update")
            ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def update(self, document_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(document_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)

    async def delete(self, document_id: str) -> None:
        await asyncio.to_thread(self._collection.document(document_id).delete)

    async def get(self, document_id: str, **get_kwargs: Any) -> VendorProduct | None:
        def _op() -> VendorProduct | None:
            snap = self._collection.document(document_id).get(**get_kwargs)
            if not snap.exists:
                return None
            payload = snapshot_to_model_dict(snap.id, snap.to_dict())
            return VendorProduct.model_validate(payload)

        return await asyncio.to_thread(_op)

    async def list_active_by_product(self, product_id: str, *, limit: int = 10) -> list[VendorProduct]:
        def _op() -> list[VendorProduct]:
            query = (
                self._collection.where(filter=FieldFilter("productId", "==", product_id))
                .where(filter=FieldFilter("active", "==", True))
                .limit(limit)
            )
            return [
                VendorProduct.model_validate(snapshot_to_model_dict(s.id, s.to_dict()))
                for s in query.stream()
            ]

        return await asyncio.to_thread(_op)

    async def get_by_product_and_vendor(
        self, product_id: str, vendor_id: str
    ) -> VendorProduct | None:
        def _op() -> VendorProduct | None:
            query = (
                self._collection.where(filter=FieldFilter("productId", "==", product_id))
                .where(filter=FieldFilter("vendorId", "==", vendor_id))
                .where(filter=FieldFilter("active", "==", True))
                .limit(1)
            )
            results = list(query.stream())
            if not results:
                return None
            s = results[0]
            return VendorProduct.model_validate(snapshot_to_model_dict(s.id, s.to_dict()))

        return await asyncio.to_thread(_op)
