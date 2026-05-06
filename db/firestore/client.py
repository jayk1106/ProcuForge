from __future__ import annotations

from typing import Any

from google.cloud import firestore

from db.firestore.config import get_firestore_settings

_client: firestore.Client | None = None


def get_firestore_client() -> firestore.Client:
    """Return a process-wide Firestore client (sync). Uses ADC or emulator env."""
    global _client
    if _client is None:
        settings = get_firestore_settings()
        db = settings.resolved_database_id()
        kwargs: dict[str, Any] = {"project": settings.resolved_project_id()}
        if db is not None:
            kwargs["database"] = db
        _client = firestore.Client(**kwargs)
    return _client


def reset_firestore_client_for_tests() -> None:
    """Clear the cached client (tests / emulator restarts)."""
    global _client
    _client = None
