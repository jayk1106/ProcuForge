from __future__ import annotations

import asyncio

from google.cloud import firestore

from db.collections.vendor import COLLECTION_ID, Vendor
from db.firestore.serialization import snapshot_to_model_dict


class VendorRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def get(self, vendor_id: str) -> Vendor | None:
        def _op() -> Vendor | None:
            snap = self._collection.document(vendor_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return Vendor.model_validate(body)

        return await asyncio.to_thread(_op)

    async def get_many(self, vendor_ids: list[str]) -> dict[str, Vendor]:
        if not vendor_ids:
            return {}

        def _op() -> dict[str, Vendor]:
            refs = [self._collection.document(vid) for vid in vendor_ids]
            out: dict[str, Vendor] = {}
            for snap in self._collection._client.get_all(refs):
                if not snap.exists:
                    continue
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                vendor = Vendor.model_validate(body)
                out[vendor.id] = vendor
            return out

        return await asyncio.to_thread(_op)
