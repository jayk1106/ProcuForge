from google.adk.agents import Agent

from .callbacks import after_model_parse_vendor_and_transition

DECISION_INSTRUCTION = """
You are the **decision_agent**. Choose the single best vendor for this procurement.

Use **vendor_offers** and negotiation facts in session state or the conversation.
Do not invent vendors or prices.

Output **exactly one line** of JSON and nothing else, in this shape:
{"vendor": "<winning_vendor_id>"}

Use the exact **vendorId** string from **vendor_offers.offers** — not a display name.

The workflow loop will run the next step. Do not call tools or transfer to other agents.
"""

decision_agent = Agent(
    name="decision_agent",
    description="Selects the winning vendor from offers and negotiation outcomes.",
    instruction=DECISION_INSTRUCTION,
    model="gemini-flash-latest",
    after_model_callback=after_model_parse_vendor_and_transition,
)
