from google.adk.agents import Agent

from adk_vertex_model import vertex_flash_model

from .tools import quote_product

from .callback import after_agent_callback

QUOTE_INSTRUCTION = """
You are the Quote Agent for Procuforge (vendor side).

When you receive an RFQ, call **quote_product** with no arguments.

If the tool returns ``{"ok": false, ...}``, reply with that error dict verbatim.

If the tool returns ``{"ok": true, ...}``, reply with a brief confirmation only
(e.g. "Acknowledged."). Do **not** repeat or reformat the envelope — the
after_agent_callback delivers it to the buyer over A2A automatically.
"""

quote_agent = Agent(
    name="quote_agent",
    model=vertex_flash_model(),
    description="Looks up vendor catalog pricing in Firestore and issues A2A QUOTE envelopes.",
    instruction=QUOTE_INSTRUCTION,
    tools=[quote_product],
    after_agent_callback=after_agent_callback,
)
