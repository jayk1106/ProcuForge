from google.adk.agents import Agent

from adk_vertex_model import vertex_flash_model

from .callbacks import (
    log_vendor_search_after_agent,
    log_vendor_search_before_agent,
    skip_vendor_search_unless_initiated,
)
from .tools import load_vendor_offers_for_product

VENDOR_SEARCH_INSTRUCTION = """
You are the **vendor_search_agent**: load supplier lines for the active procurement into state, then stop.

Steps (strict):
1. Call **load_vendor_offers_for_product** exactly once. It reads **request** from session state,
   pulls up to ten active vendor lines for `request.product_id`, drops candidates that can't meet
   the deadline / MOQ / availability, enriches survivors with buyer↔vendor relationship data, ranks
   them (contracted → preferred → relationship strength → lead time → unit price), and writes the
   top three to **vendor_offers** (`productId` + `offers`).
2. Stop after the tool returns. The tool result is a slim summary
   (`candidateCount`, `offerCount`, `filteredOut`); the offers themselves live in state and the loop
   reads them from there. Do not enumerate offers in chat. One short line acknowledging completion —
   including the filter counts if anything was dropped — is acceptable.

Never ask the user for a product id; it is already in **request**.

Tone: concise and factual.
"""

vendor_search_agent = Agent(
    name="vendor_search_agent",
    model=vertex_flash_model(),
    description="Loads supplier lines for the workflow product from the vendor catalog.",
    instruction=VENDOR_SEARCH_INSTRUCTION,
    tools=[load_vendor_offers_for_product],
    before_agent_callback=[
        skip_vendor_search_unless_initiated,
        log_vendor_search_before_agent,
    ],
    after_agent_callback=log_vendor_search_after_agent,
)
