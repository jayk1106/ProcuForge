"""Tools for decision_agent: persist the vendor selection into session state."""

from __future__ import annotations

import logging

from google.adk.tools.base_tool import ToolContext

from ...pr_status import PrStatus
from ...pr_status_transitions import transition_after_decision
from ...escalation import maybe_notify_only
from ...state_keys import PR_STATUS_KEY, SELECTED_VENDOR_KEY

_LOG = logging.getLogger(__name__)

VALID_OUTCOMES = {"ACCEPTED", "WALKED_AWAY"}


async def select_vendor(
    vendor_id: str,
    final_price: float,
    outcome: str,
    tool_context: ToolContext,
) -> dict:
    """Persist the winning vendor decision and advance pr_status to VENDOR_SELECTED.

    Args:
        vendor_id: Exact vendorId string from vendor_offers.offers.
        final_price: Agreed unit price (from buyer ACCEPT payload.unit_price,
            or walkaway reference price in the all-walkaway fallback).
        outcome: "ACCEPTED" when a vendor accepted the price; "WALKED_AWAY"
            only in the all-walkaway fallback.
    """
    vendor_id = (vendor_id or "").strip()
    if not vendor_id:
        return {"ok": False, "error": "vendor_id must be a non-empty string"}

    if not isinstance(final_price, (int, float)) or final_price <= 0:
        return {"ok": False, "error": "final_price must be a positive number"}

    outcome = (outcome or "").strip().upper()
    if outcome not in VALID_OUTCOMES:
        return {
            "ok": False,
            "error": f"outcome must be one of {sorted(VALID_OUTCOMES)}, got {outcome!r}",
        }

    decision = {
        "vendor": vendor_id,
        "final_price": round(float(final_price), 2),
        "outcome": outcome,
    }

    if outcome == "WALKED_AWAY":
        # All vendors walked away — set terminal status directly. We deliberately
        # do NOT write selected_vendor: there is no winner, so leaving it unset
        # keeps the UI honest and prevents downstream consumers (purchase_manager,
        # ui_mappers) from rendering a "selected" vendor that never agreed.
        tool_context.state[PR_STATUS_KEY] = PrStatus.NO_VENDOR_AVAILABLE.value
        maybe_notify_only(
            tool_context.state,
            source="no_vendor_available",
            reason="All vendors walked away or rejected terms — no vendor selected",
        )
        _LOG.info(
            "decision_agent: no_vendor_available all_walked_away reference_vendor=%s",
            vendor_id,
        )
        return {
            "ok": True,
            "note": "no vendor accepted; pr_status set to NO_VENDOR_AVAILABLE; selected_vendor left unset",
        }

    tool_context.state[SELECTED_VENDOR_KEY] = decision
    transition_after_decision(tool_context.state)

    _LOG.info(
        "decision_agent: vendor_selected vendor=%s final_price=%s outcome=%s",
        vendor_id,
        decision["final_price"],
        outcome,
    )
    return {"ok": True, "selected_vendor": decision}
