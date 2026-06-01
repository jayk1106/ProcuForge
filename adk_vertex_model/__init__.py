"""Vertex AI model ids for Google ADK agents.

Gemini API aliases such as ``gemini-flash-latest`` are not valid on Vertex
publisher models. Use versioned ids (e.g. ``gemini-2.0-flash``) or override
via the ``MODEL`` environment variable.
"""

from __future__ import annotations

import os

# Default flash model for Vertex AI in ratelx-ai / us-central1.
DEFAULT_VERTEX_FLASH_MODEL = "gemini-2.5-flash"


def vertex_flash_model() -> str:
    """Return the flash model id for ADK ``Agent(model=...)`` on Vertex."""
    return os.environ.get("MODEL", DEFAULT_VERTEX_FLASH_MODEL)
