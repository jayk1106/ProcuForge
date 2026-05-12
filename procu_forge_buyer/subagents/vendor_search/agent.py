from google.adk.agents import Agent

from .callbacks import (
    log_vendor_search_after_agent,
    log_vendor_search_before_agent,
    skip_vendor_search_unless_initiated,
)
from .tools import load_vendor_offers_for_product

VENDOR_SEARCH_INSTRUCTION = """
You are the **vendor_search_agent**: load supplier lines for the active procurement into state, then stop.

Steps (strict):
1. Call **load_vendor_offers_for_product** exactly once. It reads **request.product_id** from session
   state, fetches up to three active lines, and writes **vendor_offers** (`productId` + `offers` only).
2. Stop after writing **vendor_offers**. Do not enumerate offers in chat—the loop reads **vendor_offers**
   from state. At most one short line that the step completed (and whether the tool reported success)
   is acceptable.

Never ask the user for a product id; it is already in **request**.

Tone: concise and factual.
"""

vendor_search_agent = Agent(
    name="vendor_search_agent",
    model="gemini-flash-latest",
    description="Loads supplier lines for the workflow product from the vendor catalog.",
    instruction=VENDOR_SEARCH_INSTRUCTION,
    tools=[load_vendor_offers_for_product],
    before_agent_callback=[
        skip_vendor_search_unless_initiated,
        log_vendor_search_before_agent,
    ],
    after_agent_callback=log_vendor_search_after_agent,
)
