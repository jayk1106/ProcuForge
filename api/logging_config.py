"""Application logging setup so library loggers (e.g. ``procu_forge_buyer``) reach the console."""

from __future__ import annotations

import logging
import sys


def configure_app_logging() -> None:
    """Ensure ``procu_forge_buyer.*`` INFO logs are visible under uvicorn/FastAPI.

    Uvicorn configures its own loggers; the root logger often stays at WARNING with no
    handler suitable for app namespaces, so ``logger.info`` from callbacks would be dropped.
    We attach a single stream handler to the buyer package logger and avoid double emission.
    """
    pkg = logging.getLogger("procu_forge_buyer")
    if pkg.handlers:
        pkg.setLevel(logging.INFO)
        return
    pkg.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(levelname)s [%(name)s] %(message)s"),
    )
    pkg.addHandler(handler)
    pkg.propagate = False
