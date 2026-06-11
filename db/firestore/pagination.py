"""Cursor encode/decode for keyset pagination on Firestore queries.

Cursors are base64-url-encoded JSON arrays of the values passed to
``Query.start_after(*values)``. The shape is opaque to clients; only the
issuing repo knows the order of fields it expects back.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> list[Any] | None:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        values = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    return values if isinstance(values, list) else None
