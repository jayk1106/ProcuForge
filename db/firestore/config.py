from __future__ import annotations

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FirestoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_cloud_project: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLOUD_PROJECT", "GOOGLE_PROJECT_ID"),
    )

    firestore_database_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FIRESTORE_DATABASE_ID", "GOOGLE_FIRESTORE_DATABASE_ID"),
        description=(
            "Optional Firestore database id (multi-db). Leave unset to use the project's "
            "default database. Use '(default)' to force the default explicitly."
        ),
    )

    def resolved_project_id(self) -> str:
        if self.google_cloud_project:
            return self.google_cloud_project
        if os.environ.get("FIRESTORE_EMULATOR_HOST"):
            return os.environ.get("FIRESTORE_EMULATOR_PROJECT_ID", "demo-procuforge")
        raise ValueError(
            "Set GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID (or use the Firestore "
            "emulator with FIRESTORE_EMULATOR_HOST and optionally "
            "FIRESTORE_EMULATOR_PROJECT_ID)."
        )

    def resolved_database_id(self) -> str | None:
        """Return ``database`` for ``firestore.Client``, or ``None`` for the default DB."""
        if self.firestore_database_id is None:
            return None
        raw = self.firestore_database_id.strip()
        if raw == "" or raw == "(default)":
            return None
        return raw


def get_firestore_settings() -> FirestoreSettings:
    return FirestoreSettings()
