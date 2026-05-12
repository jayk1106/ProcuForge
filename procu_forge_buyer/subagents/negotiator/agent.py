import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool

from ...instruction_from_markdown import negotiator_instruction_from_default_markdown
from .callbacks import (
    log_negotiator_before_agent,
    negotiator_after_agent_with_transition,
    negotiator_after_tool,
    negotiator_before_tool,
)

load_dotenv()

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001/a2a/procu_forge_vendor{AGENT_CARD_WELL_KNOWN_PATH}",
)

vendor_remote_agent = RemoteA2aAgent(
    name="procu_forge_vendor",
    description="External vendor agent reachable over A2A; issues quotes and negotiates.",
    agent_card=VENDOR_AGENT_CARD_URL,
)

vendor_remote_agent_tool = AgentTool(agent=vendor_remote_agent)

NEGOTIATOR_INSTRUCTION_SUFFIX = """

---

## Session state (payload construction)

Session **request** holds `product_id`, `quantity`, `currency`, `required_by_date`, `budget_ceiling`, `urgency`, `delivery`, `buyer_notes`. Prefer these when filling envelope **payload** fields; do not invent catalog data.

After negotiation completes, record a concise outcome in the conversation (quote identifiers, agreed prices, lead times, vendor confirmation references when present) and stop. The workflow loop will advance **pr_status**.
"""

NEGOTIATOR_INSTRUCTION = (
    negotiator_instruction_from_default_markdown() + NEGOTIATOR_INSTRUCTION_SUFFIX
)

negotiator_agent = Agent(
    name="negotiator_agent",
    model="gemini-flash-latest",
    description="Negotiates quotes with external vendors over the A2A protocol.",
    instruction=NEGOTIATOR_INSTRUCTION,
    tools=[vendor_remote_agent_tool],
    before_agent_callback=log_negotiator_before_agent,
    after_agent_callback=negotiator_after_agent_with_transition,
    before_tool_callback=negotiator_before_tool,
    after_tool_callback=negotiator_after_tool,
)
