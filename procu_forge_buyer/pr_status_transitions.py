"""Update ``session.state`` ``pr_status`` as the procurement workflow advances."""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping

from .pr_status import PrStatus
from .state_keys import (
    NEGOTIATION_CONFIG_KEY,
    PR_STATUS_KEY,
    PREVIOUS_PR_STATUS_KEY,
    VENDOR_OFFERS_KEY,
)

logger = logging.getLogger(__name__)

_STATUS_CHANGED_BANNER = "------ status changed -----"

TERMINAL_PR_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.COMPLETED,
        PrStatus.CANCELLED,
        PrStatus.NO_VENDORS_DISCOVERED,
        PrStatus.NO_VENDOR_AVAILABLE,
    }
)

HUMAN_GATED_PR_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.ESCALATED,
        PrStatus.AWAITING_USER_APPROVAL,
        PrStatus.READY_FOR_PAYMENT,
        # Vendor-driven or external-trigger states: stop the loop, require API action to resume
        PrStatus.AWAITING_DELIVERY,
        PrStatus.GOODS_RECEIVED,
        PrStatus.AWAITING_INVOICE,
        PrStatus.INVOICE_CORRECTION_PENDING,
        PrStatus.INVOICE_VERIFIED,
        PrStatus.PO_REJECTED,
    }
)

STOP_PR_STATUSES: frozenset[PrStatus] = TERMINAL_PR_STATUSES | HUMAN_GATED_PR_STATUSES

_NEGOTIATION_SOURCE_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NEGOTIATION_IN_PROGRESS,
    }
)

_INITIATION_PHASE: frozenset[PrStatus] = frozenset(
    {
        PrStatus.INITIATED,
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NO_VENDORS_DISCOVERED,
    }
)


def _parse_current(raw: object | None) -> PrStatus:
    if raw is None or raw == "":
        return PrStatus.INITIATED
    if isinstance(raw, PrStatus):
        return raw
    try:
        return PrStatus(str(raw))
    except ValueError:
        return PrStatus.INITIATED


def _set(state: MutableMapping[str, Any], current: PrStatus, new: PrStatus) -> None:
    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info("pr_status %s -> %s", current.value, new.value)


# ── vendor discovery ──────────────────────────────────────────────────────────

def transition_after_vendor_discovery(
    state: MutableMapping[str, Any],
    *,
    offer_count: int,
) -> None:
    """Set VENDORS_DISCOVERED or NO_VENDORS_DISCOVERED after offers load."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current not in _INITIATION_PHASE:
        return

    new = PrStatus.VENDORS_DISCOVERED if offer_count > 0 else PrStatus.NO_VENDORS_DISCOVERED
    if new == current:
        return
    _set(state, current, new)


# ── negotiation ───────────────────────────────────────────────────────────────

def _targeted_vendor_ids(state: Mapping[str, Any]) -> list[str]:
    """Return the vendor ids the negotiator is expected to work through.

    Resolution order:
    1. ``vendor_offers.vendor_ids`` (array) if present and non-empty.
    2. ``vendor_offers.vendor_id`` or ``vendor_offers.vendor`` (single id) if present.
    3. Every ``vendorId`` / ``vendor_id`` from ``vendor_offers.offers``.
    """
    block = state.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return []

    explicit_list = block.get("vendor_ids")
    if isinstance(explicit_list, list):
        ids = [str(v).strip() for v in explicit_list if str(v or "").strip()]
        if ids:
            return ids

    single = block.get("vendor_id") or block.get("vendor")
    if isinstance(single, str) and single.strip():
        return [single.strip()]

    offers = block.get("offers")
    if not isinstance(offers, list):
        return []

    ids: list[str] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        vid = offer.get("vendorId") or offer.get("vendor_id")
        if isinstance(vid, str) and vid.strip():
            ids.append(vid.strip())
    return ids


def transition_to_negotiation_in_progress(state: MutableMapping[str, Any]) -> None:
    """Flip VENDORS_DISCOVERED -> NEGOTIATION_IN_PROGRESS at negotiator start.

    Idempotent: no-op if already ``NEGOTIATION_IN_PROGRESS`` or past it.
    """
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.VENDORS_DISCOVERED:
        return
    _set(state, current, PrStatus.NEGOTIATION_IN_PROGRESS)


def transition_after_negotiation(state: MutableMapping[str, Any]) -> None:
    """Advance to NEGOTIATION_IN_PROGRESS or NEGOTIATION_COMPLETED.

    Reads ``negotiation_config`` and the targeted vendor set (see
    :func:`_targeted_vendor_ids`). The status advances to
    ``NEGOTIATION_COMPLETED`` only when **every** targeted vendor has a
    terminal config entry (``done == True``, set when the buyer sends a closing
    ``ACCEPT`` / ``WALKAWAY``). Otherwise the status sits at
    ``NEGOTIATION_IN_PROGRESS`` so ``pr_router`` keeps delegating back to
    ``negotiator_agent``.
    """
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current not in _NEGOTIATION_SOURCE_STATUSES:
        return

    targeted = _targeted_vendor_ids(state)
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}

    if not targeted:
        all_done = False
    else:
        all_done = all(
            isinstance(nego.get(vid), dict) and nego[vid].get("done")
            for vid in targeted
        )

    new = PrStatus.NEGOTIATION_COMPLETED if all_done else PrStatus.NEGOTIATION_IN_PROGRESS
    if new.value == state.get(PR_STATUS_KEY):
        return
    _set(state, current, new)


# ── decision ──────────────────────────────────────────────────────────────────

def transition_after_decision(state: MutableMapping[str, Any]) -> None:
    """NEGOTIATION_COMPLETED -> VENDOR_SELECTED."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.VENDOR_SELECTED:
        return
    if current != PrStatus.NEGOTIATION_COMPLETED:
        return
    _set(state, current, PrStatus.VENDOR_SELECTED)


# ── purchase flow ─────────────────────────────────────────────────────────────

def transition_to_awaiting_user_approval(state: MutableMapping[str, Any]) -> None:
    """VENDOR_SELECTED -> AWAITING_USER_APPROVAL (human gate before PO issuance)."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.VENDOR_SELECTED:
        return
    _set(state, current, PrStatus.AWAITING_USER_APPROVAL)


def transition_to_po_acknowledged(state: MutableMapping[str, Any]) -> None:
    """PO_ISSUED -> PO_ACKNOWLEDGED after vendor acknowledges the PO."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.PO_ISSUED:
        return
    _set(state, current, PrStatus.PO_ACKNOWLEDGED)


def transition_to_invoice_under_verification(state: MutableMapping[str, Any]) -> None:
    """PO_ACKNOWLEDGED -> INVOICE_UNDER_VERIFICATION after GRN sent and invoice received."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.PO_ACKNOWLEDGED:
        return
    _set(state, current, PrStatus.INVOICE_UNDER_VERIFICATION)


def transition_to_completed(state: MutableMapping[str, Any]) -> None:
    """INVOICE_UNDER_VERIFICATION -> COMPLETED after PROCESS_COMPLETE is sent."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.INVOICE_UNDER_VERIFICATION:
        return
    _set(state, current, PrStatus.COMPLETED)


# ── legacy stub (superseded by specific purchase-flow transitions above) ──────

def transition_after_fulfillment(state: MutableMapping[str, Any]) -> None:
    """Deprecated stub kept for backwards compatibility. No-op."""
    pass


# ── helpers ───────────────────────────────────────────────────────────────────

def pr_status_line(state: Mapping[str, Any]) -> str:
    """Compact pr_status / previous_pr_status for log lines."""
    cur = state.get(PR_STATUS_KEY)
    prev = state.get(PREVIOUS_PR_STATUS_KEY)
    cur_s = str(cur) if cur not in (None, "") else "?"
    prev_s = str(prev) if prev not in (None, "") else "-"
    return "pr_status=%s previous_pr_status=%s" % (cur_s, prev_s)
