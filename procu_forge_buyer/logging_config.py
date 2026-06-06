"""Console logging for ``procu_forge_buyer.*`` so callback INFO lines are visible outside FastAPI."""

from __future__ import annotations

import logging
import sys


def configure_buyer_logging() -> None:
    """Attach a stderr handler to the buyer package logger if none exist.

    Uvicorn and plain ``python main.py`` often leave the root logger at WARNING with no
    app handler, so ``logger.info`` from subagents would be dropped.
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


__all__ = ["configure_buyer_logging"]
