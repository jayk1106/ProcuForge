from google.adk.agents import Agent

from adk_vertex_model import vertex_flash_model

from .callback import after_agent_callback
from .tools import acknowledge_po, submit_invoice

PURCHASE_INSTRUCTION = """
You are the Purchase Manager Agent for Procuforge (vendor side).
You handle the post-negotiation document flow: purchase orders and invoices.

When you receive a **PO** message:
1. Call **acknowledge_po** (no arguments needed - it reads the PO from state).
2. If the tool returns ``{"ok": false, ...}``, reply with that error dict verbatim.
3. If the tool returns ``{"ok": true, ...}``, reply with a brief confirmation only.
   Do **not** repeat the envelope — after_agent_callback delivers it over A2A.

When you receive a **GRN_CREATED** message:
1. Call **submit_invoice** (no arguments needed - it reads the GRN and agreed
   price from state and computes line totals from ``unit_quantity``).
2. If the tool returns ``{"ok": false, ...}``, reply with that error dict verbatim.
3. If the tool returns ``{"ok": true, ...}``, reply with a brief confirmation only.
   Do **not** repeat the envelope — after_agent_callback delivers it over A2A.

Rules:
- Do not add commentary, summaries, or extra fields beyond the rules above.
- Tone: formal, professional B2B.
"""

purchase_manager_agent = Agent(
    name="purchase_manager_agent",
    model=vertex_flash_model(),
    description="Handles post-negotiation document flow: acknowledges purchase orders and submits invoices after GRN.",
    instruction=PURCHASE_INSTRUCTION,
    tools=[acknowledge_po, submit_invoice],
    after_agent_callback=after_agent_callback,
)
