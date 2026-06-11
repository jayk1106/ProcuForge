from __future__ import annotations

import asyncio

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from db.collections.vendor_org_relation import COLLECTION_ID, VendorOrgRelation
from db.firestore.serialization import snapshot_to_model_dict

# Firestore "in" supports up to 30 disjuncts per query.
_IN_QUERY_CHUNK = 30


class VendorOrgRelationRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def list_active_for_org_by_vendor_ids(
        self, organization_id: str, vendor_ids: list[str]
    ) -> dict[str, VendorOrgRelation]:
        """Return active relations for the org, keyed by vendor_id."""
        if not vendor_ids:
            return {}

        unique_ids = list(dict.fromkeys(vendor_ids))

        def _op() -> dict[str, VendorOrgRelation]:
            out: dict[str, VendorOrgRelation] = {}
            for i in range(0, len(unique_ids), _IN_QUERY_CHUNK):
                chunk = unique_ids[i : i + _IN_QUERY_CHUNK]
                query = (
                    self._collection.where(
                        filter=FieldFilter("organizationId", "==", organization_id)
                    )
                    .where(filter=FieldFilter("active", "==", True))
                    .where(filter=FieldFilter("vendorId", "in", chunk))
                )
                for snap in query.stream():
                    body = snapshot_to_model_dict(snap.id, snap.to_dict())
                    relation = VendorOrgRelation.model_validate(body)
                    out[relation.vendor_id] = relation
            return out

        return await asyncio.to_thread(_op)
