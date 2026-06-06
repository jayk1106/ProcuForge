"""Per-thread vendor communication status state machine.

Tracks where a single RFQ thread (one vendor / one buyer) is in its lifecycle.
Stored under ``session.state[STATUS_KEY]`` and mutated only via :func:`set_status`.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from .state_keys import STATUS_KEY


logger = logging.getLogger(__name__)


class VendorThreadStatus(StrEnum):
    """Lifecycle states for a single buyer-vendor communication thread."""

    RFQ_RECEIVED = "RFQ_RECEIVED"
    QUOTE_SENT = "QUOTE_SENT"
    NEGOTIATION_IN_PROGRESS = "NEGOTIATION_IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    BUYER_WALKED_AWAY = "BUYER_WALKED_AWAY"
    VENDOR_WALKED_AWAY = "VENDOR_WALKED_AWAY"
    RFQ_CLOSED = "RFQ_CLOSED"
    PO_RECEIVED = "PO_RECEIVED"
    PO_ACKNOWLEDGED = "PO_ACKNOWLEDGED"
    GRN_RECEIVED = "GRN_RECEIVED"
    INVOICE_SUBMITTED = "INVOICE_SUBMITTED"
    COMPLETE = "COMPLETE"


# Allowed transitions: from -> set of valid next states.
# ``None`` represents the implicit "no status yet" starting point.
_ALLOWED_TRANSITIONS: dict[VendorThreadStatus | None, set[VendorThreadStatus]] = {
    None: {VendorThreadStatus.RFQ_RECEIVED},
    VendorThreadStatus.RFQ_RECEIVED: {VendorThreadStatus.QUOTE_SENT},
    VendorThreadStatus.QUOTE_SENT: {
        VendorThreadStatus.NEGOTIATION_IN_PROGRESS,
        VendorThreadStatus.ACCEPTED,
        VendorThreadStatus.BUYER_WALKED_AWAY,
        VendorThreadStatus.VENDOR_WALKED_AWAY,
        VendorThreadStatus.RFQ_CLOSED,
    },
    VendorThreadStatus.NEGOTIATION_IN_PROGRESS: {
        VendorThreadStatus.NEGOTIATION_IN_PROGRESS,
        VendorThreadStatus.ACCEPTED,
        VendorThreadStatus.BUYER_WALKED_AWAY,
        VendorThreadStatus.VENDOR_WALKED_AWAY,
        VendorThreadStatus.RFQ_CLOSED,
    },
    VendorThreadStatus.ACCEPTED: {
        VendorThreadStatus.PO_RECEIVED,
        VendorThreadStatus.RFQ_CLOSED,
    },
    VendorThreadStatus.BUYER_WALKED_AWAY: {VendorThreadStatus.RFQ_CLOSED},
    VendorThreadStatus.VENDOR_WALKED_AWAY: {VendorThreadStatus.RFQ_CLOSED},
    VendorThreadStatus.RFQ_CLOSED: set(),
    VendorThreadStatus.PO_RECEIVED: {VendorThreadStatus.PO_ACKNOWLEDGED},
    VendorThreadStatus.PO_ACKNOWLEDGED: {VendorThreadStatus.GRN_RECEIVED},
    VendorThreadStatus.GRN_RECEIVED: {VendorThreadStatus.INVOICE_SUBMITTED},
    VendorThreadStatus.INVOICE_SUBMITTED: {VendorThreadStatus.COMPLETE},
    VendorThreadStatus.COMPLETE: set(),
}


def get_status(state: Any) -> VendorThreadStatus | None:
    """Return the current thread status from session state, or ``None``."""
    raw = state.get(STATUS_KEY)
    if not raw:
        return None
    try:
        return VendorThreadStatus(raw)
    except ValueError:
        logger.warning("vendor_status_unknown  raw=%r", raw)
        return None


def set_status(state: Any, new_status: VendorThreadStatus) -> VendorThreadStatus:
    """Transition ``state[STATUS_KEY]`` to ``new_status``.

    Logs (but does not raise) when a transition is not in the allowed map so a
    misbehaving subagent can never wedge the session. The new status is always
    written so callers always observe the latest signal.
    """
    current = get_status(state)
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        logger.warning(
            "vendor_status_invalid_transition  current=%s -> new=%s",
            current,
            new_status,
        )
    state[STATUS_KEY] = str(new_status)
    logger.info("vendor_status_set  status=%s", new_status)
    return new_status


__all__ = ["VendorThreadStatus", "get_status", "set_status"]
