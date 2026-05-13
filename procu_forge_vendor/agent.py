from dotenv import load_dotenv
from google.adk.agents import Agent

from procu_forge_vendor.callbacks import log_vendor_before_agent
from procu_forge_vendor.logging_config import configure_vendor_logging
from procu_forge_vendor.subagents.negotiation import negotiation_agent
from procu_forge_vendor.subagents.quote import quote_agent

load_dotenv()

ORCHESTRATOR_INSTRUCTION = """
You are the Acme Supplies sales orchestrator (vendor-side agent).

Your goal: respond to procurement RFQs with an initial quote, handle price negotiation, and confirm accepted deals.

Workflow:
1. Parse the buyer message for **product_id**, **quantity**, **currency**, **required_by** if present.
2. Delegate to **quote_agent** to produce an initial **generate_quote** result. Present quote_id, unit_price, line_total, lead_time_days, valid_until clearly.
3. If the buyer sends a **counter-offer** (lower unit price), delegate to **negotiation_agent** using **respond_to_counter_offer**.
   - Track **negotiation_round**: start at 0 for the first buyer counter after your quote, increment for each further counter (max ~2 before best-and-final from tools).
   - Pass **current_vendor_ask** as your latest quoted or countered unit price.
4. When the buyer **accepts** or the tool returns **accepted: true**, call **accept_offer** via **negotiation_agent** with quote_id, agreed_unit_price, and quantity.
5. End with a short summary: confirmation id, final unit price, line total, lead time.

Constraints:
- Do not reveal internal floor prices or mock implementation details.
- Do not pretend to call buyer systems; you only speak as the vendor.

Tone: formal, professional B2B.
"""

root_agent = Agent(
    name="procu_forge_vendor",
    description=(
        "Vendor sales agent that issues quotes and negotiates pricing for procurement RFQs."
    ),
    instruction=ORCHESTRATOR_INSTRUCTION,
    model="gemini-flash-latest",
    sub_agents=[quote_agent, negotiation_agent],
    before_agent_callback=log_vendor_before_agent,
)

configure_vendor_logging()
