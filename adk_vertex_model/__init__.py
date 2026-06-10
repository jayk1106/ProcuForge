"""Vertex AI model ids for Google ADK agents.

Gemini API aliases such as ``gemini-flash-latest`` are not valid on Vertex
publisher models. Use versioned ids (e.g. ``gemini-2.0-flash``) or override
via the ``MODEL`` environment variable.
"""

from __future__ import annotations

import os

from google.adk.models.google_llm import Gemini
from google.genai import types

# Default flash model for Vertex AI in ratelx-ai / us-central1.
DEFAULT_VERTEX_FLASH_MODEL = "gemini-2.5-flash"


def vertex_flash_model() -> str:
    """Return the flash model id string (kept for callers that need a name)."""
    return os.environ.get("MODEL", DEFAULT_VERTEX_FLASH_MODEL)


# Retry policy for 429 RESOURCE_EXHAUSTED and other transient failures.
# Defaults exponential backoff: 2s -> 4s -> 8s -> 16s -> 32s (capped at 60s),
# with jitter to avoid synchronized retry storms across parallel subagents.
# Retries cover the default retryable set (408, 429, 5xx).
_RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=6,
    initial_delay=2.0,
    max_delay=60.0,
    exp_base=2.0,
    jitter=1.0,
)


def vertex_flash_llm() -> Gemini:
    """Return a Gemini LLM adapter with 429-aware retry options.

    Use this in ``Agent(model=...)`` so every LLM call inherits the retry
    policy below. Vertex shared capacity occasionally returns 429
    ``RESOURCE_EXHAUSTED``; without retries, a single transient 429 kills
    the agent's worker thread mid-workflow.
    """
    return Gemini(model=vertex_flash_model(), retry_options=_RETRY_OPTIONS)
