from __future__ import annotations

from typing import Any

from google.cloud.firestore import SERVER_TIMESTAMP
from pydantic import BaseModel


def model_to_firestore_dict(
    model: BaseModel,
    *,
    include_id_in_body: bool = False,
    timestamps: str | None = "create",
) -> dict[str, Any]:
    """
    Serialize a Pydantic model to a Firestore document body (camelCase keys).

    :param include_id_in_body: If False, omit ``id`` (document id is stored separately).
    :param timestamps: ``\"create\"`` — set metadata.createdAt/updatedAt to SERVER_TIMESTAMP;
        ``\"update\"`` — set only metadata.updatedAt; ``None`` — leave as in model (JSON values).
    """
    data: dict[str, Any] = model.model_dump(mode="json", by_alias=True, exclude_none=False)
    if not include_id_in_body:
        data.pop("id", None)

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    if timestamps == "create":
        metadata["createdAt"] = SERVER_TIMESTAMP
        metadata["updatedAt"] = SERVER_TIMESTAMP
        data["metadata"] = metadata
    elif timestamps == "update":
        metadata["updatedAt"] = SERVER_TIMESTAMP
        data["metadata"] = metadata

    return data


def merge_update_dict(patch: dict[str, Any]) -> dict[str, Any]:
    """Add metadata.updatedAt SERVER_TIMESTAMP for merge-set partial updates."""
    out = dict(patch)
    meta = out.get("metadata")
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["updatedAt"] = SERVER_TIMESTAMP
    out["metadata"] = meta
    return out


def snapshot_to_model_dict(snapshot_id: str, data: dict[str, Any] | None) -> dict[str, Any]:
    """Inject document id for Pydantic validation when ``id`` is not stored in the body."""
    body = dict(data or {})
    if "id" not in body:
        body["id"] = snapshot_id
    return body
