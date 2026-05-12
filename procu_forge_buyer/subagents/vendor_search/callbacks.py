"""Callbacks for vendor_search_agent (lifecycle logs)."""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from ...callbacks import (
    _plan_summary,
    _product_id,
    _request_id,
    managed_log_after_handler,
    managed_log_before_handler,
)
from ...pr_status import PrStatus
from ...pr_status_transitions import pr_status_line
from ...state_keys import PLANNER_PLAN_KEY, PR_STATUS_KEY, VENDOR_OFFERS_KEY

logger = logging.getLogger(__name__)


def skip_vendor_search_unless_initiated(callback_context: CallbackContext) -> types.Content | None:
    """Avoid re-running catalog load after discovery/negotiation (router mis-delegation)."""
    raw = callback_context.state.get(PR_STATUS_KEY)
    if raw in (None, ""):
        return None
    try:
        status = PrStatus(str(raw))
    except ValueError:
        logger.warning("vendor_search skip unknown pr_status=%r", raw)
        callback_context.actions.skip_summarization = True
        return types.Content(role="model", parts=[types.Part(text=" ")])
    if status == PrStatus.INITIATED:
        return None
    logger.info(
        "vendor_search_agent skip_wrong_phase pr_status=%s (only runs when INITIATED)",
        status.value,
    )
    callback_context.actions.skip_summarization = True
    return types.Content(role="model", parts=[types.Part(text=" ")])


def _offers_count_teaser(st: dict[str, Any]) -> str:
    block = st.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return "none"
    offers = block.get("offers")
    if not isinstance(offers, list):
        return "none"
    return str(len(offers))


def _offers_detail_block(st: dict[str, Any]) -> str:
    block = st.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return "vendor_offers: none"
    offers = block.get("offers")
    if not isinstance(offers, list) or not offers:
        return "vendor_offers: []"
    lines: list[str] = ["vendor_offers:"]
    for o in offers[:10]:
        if not isinstance(o, dict):
            continue
        vendor_id = o.get("vendorId", o.get("vendor_id"))
        unit_price = o.get("unitPrice", o.get("unit_price"))
        currency = o.get("currency")
        lead = o.get("leadTimeDays", o.get("lead_time_days"))
        availability = o.get("availabilityStatus", o.get("availability_status"))
        contracted = o.get("contracted")
        tail = " contracted" if contracted else ""
        lines.append(
            f"- vendorId={vendor_id} price={unit_price} {currency} lead={lead} availability={availability}{tail}"
        )
    if len(offers) > 10:
        lines.append(f"... ({len(offers) - 10} more)")
    return "\n".join(lines)


def _vendor_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "vendor_search_agent start session_id=%s request_id=%s product_id=%s plan=%s offer_count=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            _offers_count_teaser(st),
            pr_status_line(st),
        )
    )


def _vendor_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "vendor_search_agent end session_id=%s request_id=%s product_id=%s plan=%s offer_count=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            _offers_count_teaser(st),
            pr_status_line(st),
        )
    )


def _vendor_trailing(_ctx: CallbackContext, st: dict[str, Any]) -> list[str]:
    return [_offers_detail_block(st)]


log_vendor_search_before_agent = partial(
    managed_log_before_handler, span="VENDOR_SEARCH", detail_line=_vendor_before
)
log_vendor_search_after_agent = partial(
    managed_log_after_handler,
    span="VENDOR_SEARCH",
    detail_line=_vendor_after,
    trailing_lines=_vendor_trailing,
)

__all__ = [
    "log_vendor_search_after_agent",
    "log_vendor_search_before_agent",
    "skip_vendor_search_unless_initiated",
]
