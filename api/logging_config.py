"""Application logging setup so library loggers reach the console under uvicorn/FastAPI."""

from __future__ import annotations

from procu_forge_buyer.logging_config import configure_buyer_logging


def configure_app_logging() -> None:
    """Backward-compatible name used by ``api/main.py``."""
    configure_buyer_logging()


__all__ = ["configure_app_logging"]
