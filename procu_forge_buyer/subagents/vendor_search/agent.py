from google.adk.agents import Agent

from .tools import search_active_vendors_for_product

VENDOR_SEARCH_INSTRUCTION = """
You are the Vendor Search Agent for procurement workflows.

Your job:
1. Determine the catalog **product id** for the request. Parse it from the user or orchestrator
   message when it looks like: `Product: ... (id=<PRODUCT_ID>, brand=...)` or when the id is
   given explicitly. If only the product name appears and you cannot infer an id, ask for the
   product id once, then proceed.
2. Call **search_active_vendors_for_product** with that product id. It returns up to **3**
   active vendor-product rows from Firestore (vendorId, vendorSku, pricing, leadTimeDays,
   contracted, availabilityStatus).
3. Summarize the results clearly for the orchestrator: for each row list vendorId, unit price
   and currency, lead time in days, contracted flag, and availability. If the tool returns an
   empty list, state that no active vendors were found for that product.
4. Return control to the master/orchestrator agent with this summary so negotiation and
   decision steps can use **vendorId** as the vendor identifier.

Tone: concise and factual.
"""

vendor_search_agent = Agent(
    name="vendor_search_agent",
    model="gemini-flash-latest",
    description="Searches active vendors that can supply a given product via Firestore.",
    instruction=VENDOR_SEARCH_INSTRUCTION,
    tools=[search_active_vendors_for_product],
)
