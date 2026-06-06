from dotenv import load_dotenv
from google.adk.agents import Agent, LoopAgent

from adk_vertex_model import vertex_flash_model

from .logging_config import configure_buyer_logging
from .callbacks import (
    manage_log_after_orchestrator,
    manage_log_before_orchestrator,
    manage_log_after_pr_router,
    manage_log_before_pr_router,
    repair_purchase_status_callback,
    stop_loop_if_terminal,
)
from .subagents.vendor_search import vendor_search_agent
from .subagents.negotiator import negotiator_agent
from .subagents.decision import decision_agent
from .subagents.purchase_manager import purchase_manager_agent

load_dotenv()

PR_ROUTER_INSTRUCTION = """
You are **pr_router**, the loop controller for buyer procurement.

Read **session.state** first — especially **pr_status**, **vendor_offers**, **request**, **selected_vendor**.
Authoritative lifecycle: **docs/request_status.md**.

## Mechanism
- On each **pr_router** turn, call **transfer_to_agent** exactly once with a worker name below **unless**
  **pr_status** is terminal or human-gated (then produce no tool call — the outer loop stops from **pr_status**).
- Only **transfer_to_agent** exists; do not invent other function names.
- Do **not** write user-facing prose except what the framework requires.

## Hard rules
1. **After negotiation finishes**, **pr_status** becomes **NEGOTIATION_COMPLETED**. You MUST then call
   **transfer_to_agent** with agent name **decision_agent** — never **vendor_search_agent** and never
   **negotiator_agent** for that turn.
2. Call **vendor_search_agent** ONLY when **pr_status** is **INITIATED** AND (**vendor_offers** is
   missing or **offers** is empty). Never use **vendor_search_agent** for **VENDORS_DISCOVERED**,
   **NEGOTIATION_***, **NEGOTIATION_COMPLETED**, or any later status — control must return to you
   (**pr_router**) after each worker, then delegate forward.

## Decision table by **pr_status**
- **INITIATED** — If **vendor_offers** is missing or **offers** is empty:
  **transfer_to_agent** ``vendor_search_agent``. Otherwise **transfer_to_agent**
  ``negotiator_agent``.
- **VENDORS_DISCOVERED** — **transfer_to_agent** ``negotiator_agent``.
- **NO_VENDORS_DISCOVERED** — Do not delegate; the loop will stop via **pr_status** (terminal).
- **NEGOTIATION_IN_PROGRESS** — **transfer_to_agent** ``negotiator_agent``.
- **NEGOTIATION_COMPLETED** — **transfer_to_agent** ``decision_agent`` (required next step after negotiation).
- **NO_VENDOR_AVAILABLE** — Do not delegate; terminal.
- **VENDOR_SELECTED** — **transfer_to_agent** ``purchase_manager_agent``.
- **PO_ISSUED**, **PO_ACKNOWLEDGED**, **INVOICE_UNDER_VERIFICATION** — **transfer_to_agent**
  ``purchase_manager_agent``.
- **AWAITING_USER_APPROVAL** — **transfer_to_agent** ``purchase_manager_agent`` (legacy;
  advances to **PO_ISSUED** automatically).
- **AWAITING_DELIVERY**, **GOODS_RECEIVED**, **AWAITING_INVOICE**,
  **INVOICE_CORRECTION_PENDING**, **INVOICE_VERIFIED**, **PO_REJECTED** — Do not delegate;
  human gate or external trigger required (**pr_status** stops the loop).
- **READY_FOR_PAYMENT** — Do not delegate; human gate.
- **COMPLETED**, **CANCELLED**, **ESCALATED** — Do not delegate; terminal or handled via **pr_status**.

CONTEXT:
<pr_status>{pr_status?}</pr_status>
<request>{request?}</request>
<vendor_offers>{vendor_offers?}</vendor_offers>
<selected_vendor>{selected_vendor?}</selected_vendor>


If **pr_status** is missing, treat as **INITIATED** and apply the **INITIATED** row.
If **pr_status** is an unknown value but **vendor_offers** has **offers**: **transfer_to_agent**
``negotiator_agent`` (never **vendor_search_agent** unless you are certain you are in **INITIATED**
with empty offers). If **offers** is empty: **transfer_to_agent** ``vendor_search_agent`` only if
you infer **INITIATED**; otherwise **transfer_to_agent** ``negotiator_agent``.
"""

pr_router = Agent(
    name="pr_router",
    description=(
        "Routes the procurement workflow: reads pr_status and delegates to "
        "vendor_search, negotiator, decision, or purchase_manager. "
        "Terminal and human-gated states rely on pr_status, not exit_loop."
    ),
    instruction=PR_ROUTER_INSTRUCTION,
    model=vertex_flash_model(),
    sub_agents=[
        vendor_search_agent,
        negotiator_agent,
        decision_agent,
        purchase_manager_agent,
    ],
    before_agent_callback=[
        stop_loop_if_terminal,
        manage_log_before_pr_router,
    ],
    after_agent_callback=[
        manage_log_after_pr_router,
        repair_purchase_status_callback,
        stop_loop_if_terminal,
    ],
)

root_agent = LoopAgent(
    name="procu_forge_buyer",
    description=(
        "Buyer workflow loop: runs pr_router until pr_status is terminal/human-gated "
        "(callback), or max_iterations is reached."
    ),
    sub_agents=[pr_router],
    max_iterations=25,
    before_agent_callback=manage_log_before_orchestrator,
    after_agent_callback=manage_log_after_orchestrator,
)

configure_buyer_logging()
