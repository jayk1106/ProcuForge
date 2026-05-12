"""Console logging for ``procu_forge_vendor.*`` when running ``adk api_server`` etc."""

from __future__ import annotations

import logging
import sys


def configure_vendor_logging() -> None:
    pkg = logging.getLogger("procu_forge_vendor")
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


__all__ = ["configure_vendor_logging"]
