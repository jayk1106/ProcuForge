from __future__ import annotations

import asyncio

from google.cloud import firestore

from db.collections.user import COLLECTION_ID, User
from db.firestore.serialization import snapshot_to_model_dict


class UserRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def get(self, user_id: str) -> User | None:
        def _op() -> User | None:
            snap = self._collection.document(user_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return User.model_validate(body)

        return await asyncio.to_thread(_op)
