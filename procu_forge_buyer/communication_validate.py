"""Validate procurement A2A messages against ``schema/communication.json``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMUNICATION_SCHEMA_PATH = REPO_ROOT / "schema" / "communication.json"

_bundle: dict[str, Any] | None = None


class CommunicationSchemaError(Exception):
    """Message failed envelope or payload validation."""

    def __init__(self, message: str, *, errors: Sequence[str] | None = None):
        super().__init__(message)
        self.errors: list[str] = list(errors or [])


def _load_bundle() -> dict[str, Any]:
    global _bundle
    if _bundle is None:
        if not COMMUNICATION_SCHEMA_PATH.is_file():
            raise FileNotFoundError(
                f"communication schema missing: {COMMUNICATION_SCHEMA_PATH}"
            )
        with COMMUNICATION_SCHEMA_PATH.open(encoding="utf-8") as f:
            _bundle = json.load(f)
    return _bundle


def _collect_errors(validator: Draft7Validator, instance: Any) -> list[str]:
    lines: list[str] = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) if err.path else "<root>"
        lines.append(f"{loc}: {err.message}")
    return lines or ["validation failed"]


def validate_communication_message(message: dict[str, Any]) -> None:
    """Validate full message: envelope then type-specific payload.

    Raises:
        CommunicationSchemaError: On schema violation or unknown ``message_type``.
        FileNotFoundError: If the schema file is missing (first load).
    """
    bundle = _load_bundle()
    defs_block = bundle.get("$defs", {})
    if not isinstance(defs_block, dict):
        defs_block = {}

    envelope_schema = dict(bundle["envelope"])
    envelope_schema["$defs"] = defs_block
    v_env = Draft7Validator(envelope_schema)
    try:
        v_env.validate(message)
    except ValidationError as e:
        errors = _collect_errors(v_env, message)
        raise CommunicationSchemaError(
            f"envelope validation failed: {e.message}", errors=errors
        ) from e

    msg_type = message.get("message_type")
    messages = bundle.get("messages")
    if not isinstance(messages, dict) or msg_type not in messages:
        raise CommunicationSchemaError(f"unknown message_type: {msg_type!r}")

    entry = messages[msg_type]
    if not isinstance(entry, dict):
        raise CommunicationSchemaError(f"invalid messages entry for {msg_type!r}")
    payload_schema = entry.get("payload_schema")
    if not isinstance(payload_schema, dict):
        raise CommunicationSchemaError(f"missing payload_schema for {msg_type!r}")

    payload_combined = dict(payload_schema)
    payload_combined["$defs"] = defs_block
    v_pay = Draft7Validator(payload_combined)
    payload = message.get("payload")
    try:
        v_pay.validate(payload)
    except ValidationError as e:
        errors = _collect_errors(v_pay, payload)
        raise CommunicationSchemaError(
            f"payload validation failed for {msg_type!r}: {e.message}", errors=errors
        ) from e


__all__ = [
    "COMMUNICATION_SCHEMA_PATH",
    "CommunicationSchemaError",
    "validate_communication_message",
]
