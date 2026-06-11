import json

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext

from adk_vertex_model import vertex_flash_llm

from .callbacks import (
    negotiator_after_agent_with_transition,
    negotiator_after_tool,
    negotiator_before_agent_with_transition,
    negotiator_before_tool,
)
from .tools import build_negotiation_progress, negotiate_with_vendor

load_dotenv()


_INSTRUCTION_TEMPLATE = """# buyer_negotiator

You drive A2A negotiation with every vendor in `progress.vendors`. The progress
block below is the **authoritative state for this turn** — every per-vendor
`recommended_action` was precomputed for you. Do not recompute prices, rounds,
or message types yourself.

## Current progress (read from session.state)

```json
{progress_json}
```

## Tool

- `negotiate_with_vendor(communication_data=<dict>)` — one call per vendor.
  `communication_data` must be the vendor's `recommended_action` dict
  **passed through verbatim**, minus the read-only `reason` field. Allowed keys:
  `vendor_id`, `message_type`, `price` (COUNTER_OFFER / ACCEPT, and optional
  last price for WALKAWAY), `walkaway_reason` (WALKAWAY only).

## Algorithm — execute in a single turn

```
for vendor in progress.vendors:
    if vendor.done is true: continue
    if vendor.recommended_action is null: continue
    call negotiate_with_vendor(communication_data=vendor.recommended_action)
    # do not wait, summarise, or emit prose between calls
```

## Hard rules

- One tool call per not-done vendor per turn. Never re-call a vendor whose
  `done` already flipped true.
- Pass `recommended_action` through unchanged. Do not edit prices, invent
  fields, or guess message types. The `reason` field is informational only —
  strip it before calling the tool.
- Never produce envelope JSON yourself. `negotiate_with_vendor` builds it.
- On `{{"ok": false, ...}}` from the tool, stop the loop and return that dict
  verbatim. The orchestrator retries on the next turn.

## Termination

When `progress.all_done == true`, emit a single-line summary then stop:

```
Negotiation complete.
<vendor_id>: ACCEPTED at $<price>
<vendor_id>: WALKED_AWAY — <reason>
```

Otherwise stop after the per-vendor loop and let `pr_router` re-invoke you.
"""


def negotiator_instruction(context: ReadonlyContext) -> str:
    """Render the instruction with the per-vendor progress snapshot embedded."""
    progress = build_negotiation_progress(context.state)
    return _INSTRUCTION_TEMPLATE.format(progress_json=json.dumps(progress, indent=2))


negotiator_agent = Agent(
    name="negotiator_agent",
    model=vertex_flash_llm(),
    description="Negotiates quotes with external vendors over the A2A protocol.",
    instruction=negotiator_instruction,
    tools=[negotiate_with_vendor],
    before_agent_callback=negotiator_before_agent_with_transition,
    after_agent_callback=negotiator_after_agent_with_transition,
    before_tool_callback=negotiator_before_tool,
    after_tool_callback=negotiator_after_tool,
)
