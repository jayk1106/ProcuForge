"""Update ``session.state`` ``pr_status`` when vendor discovery completes."""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping

from .pr_status import PrStatus
from .state_keys import PR_STATUS_KEY, PREVIOUS_PR_STATUS_KEY

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


def transition_after_vendor_discovery(
    state: MutableMapping[str, Any],
    *,
    offer_count: int,
) -> None:
    """Set ``VENDORS_DISCOVERED`` or ``NO_VENDORS_DISCOVERED`` after offers load.

    Only updates when the workflow is still in the initiation phase; does not
    overwrite negotiation or later phases. When the status value changes,
    stores the prior value in ``previous_pr_status`` and logs a banner line.
    """
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current not in _INITIATION_PHASE:
        return

    new = PrStatus.VENDORS_DISCOVERED if offer_count > 0 else PrStatus.NO_VENDORS_DISCOVERED
    if new == current:
        return

    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info(
        "pr_status %s -> %s (vendor discovery, offer_count=%s)",
        current.value,
        new.value,
        offer_count,
    )


def transition_after_negotiation(state: MutableMapping[str, Any]) -> None:
    """Minimal happy path: move from discovery/negotiation to ``NEGOTIATION_COMPLETED``."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.NEGOTIATION_COMPLETED:
        return
    if current not in _NEGOTIATION_SOURCE_STATUSES:
        return

    new = PrStatus.NEGOTIATION_COMPLETED
    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info(
        "pr_status %s -> %s (negotiation complete)",
        current.value,
        new.value,
    )


def transition_after_decision(state: MutableMapping[str, Any]) -> None:
    """Minimal happy path: ``NEGOTIATION_COMPLETED`` -> ``VENDOR_SELECTED``."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.VENDOR_SELECTED:
        return
    if current != PrStatus.NEGOTIATION_COMPLETED:
        return

    new = PrStatus.VENDOR_SELECTED
    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info(
        "pr_status %s -> %s (vendor selected)",
        current.value,
        new.value,
    )


def transition_after_fulfillment(state: MutableMapping[str, Any]) -> None:
    """Minimal happy path: ``VENDOR_SELECTED`` -> ``COMPLETED`` (stub fulfillment)."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.COMPLETED:
        return
    if current != PrStatus.VENDOR_SELECTED:
        return

    new = PrStatus.COMPLETED
    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info(
        "pr_status %s -> %s (fulfillment stub complete)",
        current.value,
        new.value,
    )


def pr_status_line(state: Mapping[str, Any]) -> str:
    """Compact ``pr_status`` / ``previous_pr_status`` for log lines."""
    cur = state.get(PR_STATUS_KEY)
    prev = state.get(PREVIOUS_PR_STATUS_KEY)
    cur_s = str(cur) if cur not in (None, "") else "?"
    prev_s = str(prev) if prev not in (None, "") else "-"
    return "pr_status=%s previous_pr_status=%s" % (cur_s, prev_s)
