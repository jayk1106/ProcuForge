from google.adk.agents import Agent

from .callbacks import purchase_manager_after_agent
from .tools import (
    approve_po,
    send_grn_created,
    send_po,
    send_process_complete,
    send_rfq_closed_to_losing_vendors,
)

PURCHASE_MANAGER_INSTRUCTION = """
You are the **purchase_manager_agent** for the buyer side of procurement.

<pr_status>{pr_status?}</pr_status>
<selected_vendor>{selected_vendor?}</selected_vendor>

You handle the post-negotiation document flow with the vendor over A2A.
Read **pr_status** from session state and call **exactly one tool** per turn:

| pr_status | Tool to call |
|-----------|--------------|
| VENDOR_SELECTED | Call **send_rfq_closed_to_losing_vendors** — no arguments needed; notifies all non-selected vendors. Then output a one-line summary of the selected vendor and agreed price for human review. The callback will set AWAITING_USER_APPROVAL. |
| AWAITING_USER_APPROVAL | Call **approve_po** — no arguments needed; transitions to PO_ISSUED so the PO can be sent on the next turn. |
| PO_ISSUED | Call **send_po** — no arguments needed; reads all data from state. |
| PO_ACKNOWLEDGED | Call **send_grn_created** — no arguments needed; reads PO data from state. |
| INVOICE_UNDER_VERIFICATION | Call **send_process_complete** — no arguments needed; reads PO, GRN, and invoice from state. |

Rules:
- Call at most **one** tool per turn.
- Return the tool result **exactly** as your reply — do not summarise or reformat.
- If the tool returns ``{"ok": false, ...}``, return that error dict unchanged.
- Do not call a tool that does not match the current **pr_status**.
"""

purchase_manager_agent = Agent(
    name="purchase_manager_agent",
    description=(
        "Handles the post-negotiation A2A document flow: sends PO, GRN_CREATED, "
        "and PROCESS_COMPLETE to the vendor and advances pr_status accordingly."
    ),
    instruction=PURCHASE_MANAGER_INSTRUCTION,
    model="gemini-flash-latest",
    tools=[approve_po, send_po, send_grn_created, send_process_complete, send_rfq_closed_to_losing_vendors],
    after_agent_callback=purchase_manager_after_agent,
)
