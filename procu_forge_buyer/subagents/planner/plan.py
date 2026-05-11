from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlannerNextAction = Literal[
    "search_vendors",
    "request_quote",
    "select_vendor",
    "fulfill_purchase",
    "escalate_to_human",
    "complete",
]

PlannerAgentName = Literal[
    "vendor_search_agent",
    "negotiator_agent",
    "decision_agent",
    "purchase_manager_agent",
]


class PlannerPlan(BaseModel):
    """Structured next-step plan for the buyer orchestrator."""

    model_config = ConfigDict(extra="forbid")

    next_action: PlannerNextAction = Field(
        description="High-level workflow phase the orchestrator should execute next.",
    )
    agent_to_invoke: PlannerAgentName | None = Field(
        default=None,
        description=(
            "Sub-agent to delegate to when next_action requires delegation; "
            "null for escalate_to_human or complete."
        ),
    )
    reasoning: str = Field(
        min_length=1,
        description="Brief justification for the chosen next_action (facts from state/conversation).",
    )
    other_context: dict[str, object] = Field(
        default_factory=dict,
        description="Optional structured hints (e.g. vendor_ids, blockers).",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence in this plan.")
