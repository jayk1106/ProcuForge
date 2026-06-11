"""Lifecycle states for a single buyer↔vendor negotiation thread.

These are inferred on read from session state + the last A2A message
exchanged on the thread. They map down to the wire-level
``ActiveVendorDTO.status`` union (``NEGOTIATING | WON | LOST | WALKED_AWAY``)
via :func:`to_active_vendor_status` so the existing frontend types remain
unchanged.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


class VendorThreadStatus(str, Enum):
    INITIATED = "INITIATED"
    INVITED = "INVITED"
    QUOTED = "QUOTED"
    COUNTER_PROPOSED = "COUNTER_PROPOSED"
    AWAITING_VENDOR_RESPONSE = "AWAITING_VENDOR_RESPONSE"
    ESCALATED = "ESCALATED"
    WALKED_AWAY = "WALKED_AWAY"
    AWARDED = "AWARDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


VENDOR_THREAD_TERMINAL: frozenset[VendorThreadStatus] = frozenset(
    {
        VendorThreadStatus.WALKED_AWAY,
        VendorThreadStatus.AWARDED,
        VendorThreadStatus.REJECTED,
        VendorThreadStatus.EXPIRED,
    }
)


ActiveVendorStatus = Literal["NEGOTIATING", "WON", "LOST", "WALKED_AWAY"]


def to_active_vendor_status(status: VendorThreadStatus) -> ActiveVendorStatus:
    """Adapt the rich enum down to the frontend-facing status union."""
    if status == VendorThreadStatus.AWARDED:
        return "WON"
    if status == VendorThreadStatus.WALKED_AWAY:
        return "WALKED_AWAY"
    if status in {VendorThreadStatus.REJECTED, VendorThreadStatus.EXPIRED}:
        return "LOST"
    return "NEGOTIATING"


def to_state_label(status: VendorThreadStatus) -> str:
    """Short label used in row state columns. Maps multiple states to
    ``CLOSED`` so the existing UI does not need a new pill per enum value.
    """
    if status in VENDOR_THREAD_TERMINAL and status != VendorThreadStatus.WALKED_AWAY:
        return "CLOSED"
    if status == VendorThreadStatus.WALKED_AWAY:
        return "WALKED_AWAY"
    if status == VendorThreadStatus.ESCALATED:
        return "ESCALATED"
    return "NEGOTIATING"


def infer_vendor_thread_status(
    config: dict,
    *,
    selected_vendor_id: str | None = None,
    override: dict | None = None,
) -> VendorThreadStatus:
    """Derive a :class:`VendorThreadStatus` from the negotiation_config entry.

    ``override`` is the per-thread human-applied override (from
    ``VENDOR_THREAD_OVERRIDES_KEY``). When present and parseable, it wins
    over inferred status — that's the whole point of an override.

    Inputs are best-effort: a missing key or unexpected type falls back to
    ``INITIATED`` (rather than raising) so this stays safe on read paths.
    """
    if isinstance(override, dict):
        override_status = override.get("status")
        if isinstance(override_status, str):
            try:
                return VendorThreadStatus(override_status)
            except ValueError:
                pass

    if not isinstance(config, dict):
        return VendorThreadStatus.INITIATED

    vendor_id = str(config.get("vendor_id") or "")
    explicit = config.get("status")
    if isinstance(explicit, str):
        try:
            return VendorThreadStatus(explicit)
        except ValueError:
            pass

    if config.get("escalated"):
        return VendorThreadStatus.ESCALATED

    comms = config.get("communications")
    comms_list = comms if isinstance(comms, list) else []
    last_dict: dict | None = None
    for entry in reversed(comms_list):
        if isinstance(entry, dict):
            last_dict = entry
            break

    if selected_vendor_id and vendor_id == selected_vendor_id:
        return VendorThreadStatus.AWARDED

    if config.get("done"):
        last_type = str(last_dict.get("message_type") if last_dict else "") or ""
        if last_type == "WALKAWAY":
            return VendorThreadStatus.WALKED_AWAY
        # Once a vendor has been picked, every other closed thread is a loss
        # for this vendor — even if they accepted the buyer's offer.
        if selected_vendor_id:
            return VendorThreadStatus.REJECTED
        # Rounds are done but decision_agent has not recorded a winner yet.
        # Hold at AWAITING_VENDOR_RESPONSE so the UI does not promote any
        # vendor to WON prematurely — the board keeps showing them as
        # negotiating until ``selected_vendor`` lands in state.
        return VendorThreadStatus.AWAITING_VENDOR_RESPONSE

    if not comms_list:
        return VendorThreadStatus.INITIATED

    last_type = str(last_dict.get("message_type") if last_dict else "")
    last_from = str(last_dict.get("from_agent") if last_dict else "")

    if last_type == "RFQ":
        return VendorThreadStatus.INVITED
    if last_type == "QUOTE":
        return VendorThreadStatus.QUOTED
    if last_type == "COUNTER_OFFER":
        return (
            VendorThreadStatus.AWAITING_VENDOR_RESPONSE
            if last_from != "vendor_agent"
            else VendorThreadStatus.COUNTER_PROPOSED
        )
    return VendorThreadStatus.QUOTED
