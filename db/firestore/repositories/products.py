from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from db.collections.product import COLLECTION_ID, Product
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class ProductRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def create(self, product: Product, **write_kwargs: Any) -> None:
        def _op() -> None:
            ref = self._collection.document(product.id)
            data = model_to_firestore_dict(product, include_id_in_body=False, timestamps="create")
            ref.create(data, **write_kwargs)

        await asyncio.to_thread(_op)

    async def replace(self, product: Product) -> None:
        def _op() -> None:
            ref = self._collection.document(product.id)
            data = model_to_firestore_dict(product, include_id_in_body=False, timestamps="update")
            ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def update(self, document_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(document_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)

    async def delete(self, document_id: str) -> None:
        await asyncio.to_thread(self._collection.document(document_id).delete)

    async def get(self, document_id: str, **get_kwargs: Any) -> Product | None:
        def _op() -> Product | None:
            snap = self._collection.document(document_id).get(**get_kwargs)
            if not snap.exists:
                return None
            payload = snapshot_to_model_dict(snap.id, snap.to_dict())
            return Product.model_validate(payload)

        return await asyncio.to_thread(_op)

    async def list_active(self, *, limit: int = 100) -> list[Product]:
        """Return active catalog products (bounded scan).

        Suitable for small catalogs; large catalogs need indexed search or an external engine.
        """

        def _op() -> list[Product]:
            query = (
                self._collection.where(filter=FieldFilter("active", "==", True)).limit(limit)
            )
            return [
                Product.model_validate(snapshot_to_model_dict(s.id, s.to_dict()))
                for s in query.stream()
            ]

        return await asyncio.to_thread(_op)

    async def list_active(self, *, limit: int = 100) -> list[Product]:
        """Return active catalog products (bounded scan).

        Suitable for small catalogs; large catalogs need indexed search or an external engine.
        """

        def _op() -> list[Product]:
            query = (
                self._collection.where(filter=FieldFilter("active", "==", True)).limit(limit)
            )
            return [
                Product.model_validate(snapshot_to_model_dict(s.id, s.to_dict()))
                for s in query.stream()
            ]

        return await asyncio.to_thread(_op)
