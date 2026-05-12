"""Callbacks for purchase_manager_agent: advance ``pr_status`` after stub fulfillment."""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext

from ...pr_status_transitions import transition_after_fulfillment


def purchase_manager_after_agent(callback_context: CallbackContext) -> None:
    transition_after_fulfillment(callback_context.state)
    return None
