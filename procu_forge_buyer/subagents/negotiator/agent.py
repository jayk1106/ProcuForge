import os

from dotenv import load_dotenv
from google.adk.agents import Agent

from adk_vertex_model import vertex_flash_model
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool

from .callbacks import (
    negotiator_after_agent_with_transition,
    negotiator_after_tool,
    negotiator_before_agent_with_transition,
    negotiator_before_tool,
)
from .tools import negotiate_with_vendor

load_dotenv()

# VENDOR_AGENT_CARD_URL = os.getenv(
#     "VENDOR_A2A_AGENT_CARD_URL",
#     f"http://127.0.0.1:8001/a2a/procu_forge_vendor{AGENT_CARD_WELL_KNOWN_PATH}",
# )

# vendor_remote_agent = RemoteA2aAgent(
#     name="procu_forge_vendor",
#     description="External vendor agent reachable over A2A; issues quotes and negotiates.",
#     agent_card=VENDOR_AGENT_CARD_URL,
# )

# vendor_remote_agent_tool = AgentTool(agent=vendor_remote_agent)

NEGOTIATOR_INSTRUCTION = """# buyer_negotiator

You negotiate prices with **every** vendor in `vendor_offers.offers` over A2A, working
through **all** not-yet-done vendors in **each** agent turn.
Use `negotiate_with_vendor` for every outbound message. Never produce envelope JSON yourself.

---

## Session state (read-only inputs)

<request>{request?}</request>
<vendor_offers>{vendor_offers?}</vendor_offers>
<negotiation_config>{negotiation_config?}</negotiation_config>

**`vendor_offers.offers`** — list of candidate vendors. Each offer's `vendorId` is the
`vendor_id` you pass to the tool.

**`request`** — carries `product_id`, `quantity`, `currency`, `required_by_date`,
`budget_ceiling`, `urgency`, `delivery`, `buyer_notes`.

**`negotiation_config[<vendor_id>]`** — per-vendor resume state maintained by the tool:
- `done` — `true` once you have sent `ACCEPT` or `WALKAWAY` for that vendor.
- `round` — last round of the **last buyer-sent** message (`None` before RFQ, `0` after RFQ,
  then 1..3).
- `target_price` — buyer's target unit price for this vendor.
- `communications` — chronological list; each `negotiate_with_vendor` call appends **two**
  entries: the buyer's outbound message (even index) and the vendor's reply (odd index /
  `communications[-1]`). **On re-entry turns, read the vendor's last reply from
  `communications[-1]` — the tool's `vendor_reply` return value is only valid for the
  current call.**

---

## Algorithm for each turn

Execute the following loop. You **must** call `negotiate_with_vendor` for **every** not-done
vendor before finishing your turn.

```
for each offer in vendor_offers.offers:
    vendor_id = offer.vendorId

    # Skip vendors already closed
    if negotiation_config[vendor_id].done == true:
        continue

    # Determine next move
    if negotiation_config[vendor_id] is missing OR communications is empty:
        next_move = RFQ

    else:
        last = negotiation_config[vendor_id].communications[-1]  # vendor's last reply

        # Guard: if last entry is buyer-outbound (message_type in RFQ/COUNTER_OFFER/ACCEPT/WALKAWAY)
        # and done is still false, skip this vendor this turn.
        if last.message_type in {RFQ, COUNTER_OFFER, ACCEPT, WALKAWAY}:
            continue

        vendor_price  = last.payload.unit_price OR last.payload.proposed_unit_price
        is_final      = last.payload.is_final (default false)
        decision      = last.payload.decision  # only on COUNTER_RESPONSE: COUNTER | HOLD | REJECT
        target_price  = negotiation_config[vendor_id].target_price
        round         = negotiation_config[vendor_id].round

        # Edge cases (check first)
        if last.payload.response_deadline is in the past:
            next_move = WALKAWAY(QUOTE_EXPIRED)
        elif last.payload.currency != request.currency:
            next_move = WALKAWAY(PRICE_GAP_TOO_LARGE)

        # Decision rules (first match wins)
        elif last_type == WALKAWAY:
            next_move = WALKAWAY(VENDOR_REJECTED, price=vendor_price)
        elif last_type == ACCEPT:
            next_move = ACCEPT(vendor_price)
        elif last_type == COUNTER_RESPONSE AND decision == REJECT:
            next_move = WALKAWAY(VENDOR_REJECTED, price=vendor_price)
        elif vendor_price <= target_price:
            next_move = ACCEPT(vendor_price)
        elif round >= 3 OR is_final == true:
            next_move = WALKAWAY(MAX_ROUNDS_REACHED, price=vendor_price)
        else:
            next_move = COUNTER_OFFER(max(target_price, vendor_price * 0.92))

    # Execute — one tool call per vendor
    negotiate_with_vendor(communication_data={
        "vendor_id": vendor_id,
        "message_type": next_move,
        "price": <required for COUNTER_OFFER and ACCEPT; optional last_offer for WALKAWAY>,
        "walkaway_reason": <required only for WALKAWAY>,
    })
```

**Do not emit any prose between tool calls.** The tool updates `negotiation_config`
automatically after each call. Continue to the next vendor immediately after each call
completes — do not wait or summarise between calls.

---

## Tool contract: `negotiate_with_vendor`

Arguments (pass as `communication_data`):
- `vendor_id` — must match a `vendorId` in `vendor_offers.offers`.
- `message_type` — one of `RFQ`, `COUNTER_OFFER`, `ACCEPT`, `WALKAWAY`.
- `price` — **required** for `COUNTER_OFFER` / `ACCEPT`; optional last-offer for `WALKAWAY`.
- `walkaway_reason` — **required** for `WALKAWAY`: `PRICE_GAP_TOO_LARGE`,
  `MAX_ROUNDS_REACHED`, `VENDOR_REJECTED`, `BUYER_CANCELLED`, `QUOTE_EXPIRED`.

Rules:
- A vendor thread must start with `RFQ` — any other type before RFQ is rejected by the tool.
- One vendor per call; call the tool separately for each vendor.
- On `ok: false` in the tool response → send `WALKAWAY(VENDOR_REJECTED)` for that vendor in
  the same turn to close the thread.

---

## Termination

After the loop above, if **every** vendor in `vendor_offers.offers` has
`negotiation_config[vendor_id].done == true`, emit a brief summary then stop:

```
Negotiation complete.
<vendor_id>: ACCEPTED at $<price> (round <N>)
<vendor_id>: WALKED_AWAY — <reason>
...
```

Do not call any tool after the summary. The workflow callback advances `pr_status` automatically.

If any vendor is still not done after the loop (some were skipped via the guard), do **not**
emit the summary — the outer loop will re-invoke you on the next iteration to finish them.
"""

negotiator_agent = Agent(
    name="negotiator_agent",
    model=vertex_flash_model(),
    description="Negotiates quotes with external vendors over the A2A protocol.",
    instruction=NEGOTIATOR_INSTRUCTION,
    tools=[negotiate_with_vendor],
    before_agent_callback=negotiator_before_agent_with_transition,
    after_agent_callback=negotiator_after_agent_with_transition,
    before_tool_callback=negotiator_before_tool,
    after_tool_callback=negotiator_after_tool,
)
