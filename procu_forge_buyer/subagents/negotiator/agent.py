import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool

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

negotiator_agent = Agent(
    name="negotiator_agent",
    model="gemini-flash-latest",
    description="Negotiates quotes with external vendors over the A2A protocol.",
    instruction="""
    You are the **buyer-side** negotiator. You communicate with external vendors over A2A.

    For each candidate vendor line or RFQ the orchestrator gives you:
      1. Message the external party **procu_forge_vendor** and request a quote. Include:
         product_id, quantity, currency, required_by (if known), and any constraints (budget/urgency).
      2. After the vendor returns a quote (unit_price, quote_id, lead_time_days), propose a
         counter-offer at roughly **92%** of their quoted unit price (rounded sensibly), unless
         their price already meets budget—then you may accept.
      3. Continue the dialogue with **procu_forge_vendor** until they accept your price,
         you accept their final offer, or they state **best and final**. Then stop countering.
      4. Repeat the above for multiple vendors when the orchestrator provides multiple vendor options.
         Keep a small table of outcomes internally.
      5. When terms are agreed, ensure the vendor confirms (accept_offer / confirmation id) and
         return a negotiation summary for the master agent:
         - quote_id (if any)
         - agreed unit_price and line total (unit_price × quantity)
         - lead_time_days
         - vendor_confirmation_id or reference from the vendor

    Rules:
    - The vendor is a separate party. Do not \"delegate\" your job to them; you remain responsible
      for driving the negotiation.
    - Do not invent vendor replies; only use what **procu_forge_vendor** returns.
    - Keep tone professional. Return structured numbers when the vendor provides them.

    After negotiation completes, transfer control back to the master/orchestrator agent.
    """,
   #  sub_agents=[vendor_remote_agent],
   tools=[vendor_remote_agent_tool],
)
