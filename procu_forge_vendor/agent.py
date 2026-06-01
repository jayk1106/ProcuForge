from dotenv import load_dotenv
from google.adk.agents import Agent

from adk_vertex_model import vertex_flash_model

from procu_forge_vendor.callbacks import before_agent_callback
from procu_forge_vendor.logging_config import configure_vendor_logging
from procu_forge_vendor.subagents.negotiation import negotiation_agent
from procu_forge_vendor.subagents.purchase import purchase_manager_agent
from procu_forge_vendor.subagents.quote import quote_agent

load_dotenv()

ORCHESTRATOR_INSTRUCTION = """
You are the Acme Supplies sales orchestrator (vendor-side agent).

Your goal: route incoming buyer messages to the correct sub-agent based on the message type.

Routing rules:
- **RFQ** -> delegate to **quote_agent** to produce an initial quote via `quote_product`.
- **COUNTER_OFFER** or **ACCEPT** -> delegate to **negotiation_agent** to handle pricing via `get_negotiation_context` and `send_response`.
- **PO** -> delegate to **purchase_manager_agent** to acknowledge the PO via `acknowledge_po`.
- **GRN_CREATED** -> delegate to **purchase_manager_agent** to submit an invoice via `submit_invoice`.

No-response message types (handled by `before_agent_callback`, do not delegate):
- **WALKAWAY** (from buyer) - buyer ended the negotiation; thread is auto-closed.
- **RFQ_CLOSED** - thread closure acknowledgement only.
- **PROCESS_COMPLETE** - lifecycle terminator, no envelope sent back.

Constraints:
- Do not generate any response yourself - always delegate to the appropriate sub-agent.
- Do not reveal internal floor prices or implementation details.
- Tone: formal, professional B2B.
"""

root_agent = Agent(
    name="procu_forge_vendor",
    description=(
        "Vendor sales agent that issues quotes and negotiates pricing for procurement RFQs."
    ),
    instruction=ORCHESTRATOR_INSTRUCTION,
    model=vertex_flash_model(),
    sub_agents=[quote_agent, negotiation_agent, purchase_manager_agent],
    before_agent_callback=before_agent_callback,
)

configure_vendor_logging()
