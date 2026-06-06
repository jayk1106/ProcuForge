from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from adk_vertex_model import vertex_flash_model

from .callbacks import (
    inject_planner_session_state_before_model,
    log_planner_after_agent,
    log_planner_before_agent,
)
from ...state_keys import PLANNER_PLAN_KEY

from .plan import PlannerPlan

PLANNER_INSTRUCTION = """
You are the procurement **Planner**. No tools, no sub-agents—emit exactly one **PlannerPlan**
(JSON schema) per call.

## Inputs (precedence)
1. A **session.state** JSON blob is injected as a user message before this call—treat it as
   ground truth for **request**, **product**, **current_plan** (your prior output), and **vendor_offers**.
2. The orchestrator may also pass a short tool string—if it conflicts with the JSON, **prefer the JSON**.

## Route to these agents only (names must match **agent_to_invoke**)
- **vendor_search_agent** — loads **vendor_offers** from **request.product_id**. Choose **search_vendors**
  when **vendor_offers** is missing, empty, or must be refreshed.
- **negotiator_agent** — A2A RFQ/negotiation with **procu_forge_vendor**. Choose **request_quote** when
  **vendor_offers.offers** is non-empty and quotes are not yet settled.
- **decision_agent** — pick best vendor. Choose **select_vendor** when comparable offer summaries exist.
- **purchase_manager_agent** — PO + delivery/invoice stubs. Choose **fulfill_purchase** when a winner
  is chosen and fulfillment is not yet done per transcript.

## Ordering (hard)
- Never **request_quote** before you would be comfortable with supplier lines (from **vendor_offers**
  or clear transcript equivalents).
- Never **select_vendor** without negotiation-style facts to compare.
- Never **fulfill_purchase** without an explicit chosen vendor in state or transcript.
- **complete** when PO + verification are done per transcript; **agent_to_invoke** = null.
- **escalate_to_human** when blocked (no offers and no path, repeated failures, missing mandatory
  fields, policy risk, user asks for a human, or deadlock); **agent_to_invoke** = null.

## Output
- **confidence** in [0, 1] (lower when ambiguous).
- **other_context**: small hints only (e.g. vendor id list, blockers)—avoid long prose.
- **reasoning**: 1–2 sentences citing **request**, **product**, **vendor_offers**, **current_plan**, or
  the latest user/assistant turns—not generic filler.
"""

planner_agent = Agent(
    name="planner_agent",
    description=(
        "Emits a structured PlannerPlan (next_action, agent_to_invoke, reasoning, "
        "other_context, confidence) for the buyer orchestrator."
    ),
    instruction=PLANNER_INSTRUCTION,
    model=vertex_flash_model(),
    output_schema=PlannerPlan,
    output_key=PLANNER_PLAN_KEY,
    before_agent_callback=log_planner_before_agent,
    after_agent_callback=log_planner_after_agent,
    before_model_callback=inject_planner_session_state_before_model,
)

planner_tool = AgentTool(agent=planner_agent)
