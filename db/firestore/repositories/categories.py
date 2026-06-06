from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore

from db.collections.category import COLLECTION_ID, Category
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class CategoryRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def create(self, category: Category, **write_kwargs: Any) -> None:
        def _op() -> None:
            ref = self._collection.document(category.id)
            data = model_to_firestore_dict(category, include_id_in_body=False, timestamps="create")
            ref.create(data, **write_kwargs)

        await asyncio.to_thread(_op)

    async def replace(self, category: Category) -> None:
        """Replace the full document (does not preserve server timestamps on unchanged fields)."""

        def _op() -> None:
            ref = self._collection.document(category.id)
            data = model_to_firestore_dict(category, include_id_in_body=False, timestamps="update")
            ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def update(self, document_id: str, patch: dict[str, Any]) -> None:
        """Merge top-level (and nested map) fields; bumps ``metadata.updatedAt`` server-side."""

        def _op() -> None:
            ref = self._collection.document(document_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)

    async def delete(self, document_id: str) -> None:
        await asyncio.to_thread(self._collection.document(document_id).delete)

    async def get(self, document_id: str, **get_kwargs: Any) -> Category | None:
        def _op() -> Category | None:
            snap = self._collection.document(document_id).get(**get_kwargs)
            if not snap.exists:
                return None
            payload = snapshot_to_model_dict(snap.id, snap.to_dict())
            return Category.model_validate(payload)

        return await asyncio.to_thread(_op)
