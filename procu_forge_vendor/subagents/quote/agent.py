from google.adk.agents import Agent

from .tools import quote_product

QUOTE_INSTRUCTION = """
You are the Quote Agent for Procuforge (vendor side).

When you receive an RFQ, call **quote_product** with no arguments.
Return the tool's response **exactly and completely** as your reply —
do not summarise, reformat, or omit any fields.

If the tool returns ``{"ok": false, ...}``, reply with that error dict.
"""

quote_agent = Agent(
    name="quote_agent",
    model="gemini-flash-latest",
    description="Looks up vendor catalog pricing in Firestore and issues A2A QUOTE envelopes.",
    instruction=QUOTE_INSTRUCTION,
    tools=[quote_product],
)
