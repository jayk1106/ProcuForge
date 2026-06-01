"""Canonical ADK session.state keys for the buyer workflow."""

PRODUCT_KEY = "product"
REQUEST_KEY = "request"
PLANNER_PLAN_KEY = "current_plan"
VENDOR_OFFERS_KEY = "vendor_offers"
PR_STATUS_KEY = "pr_status"
PREVIOUS_PR_STATUS_KEY = "previous_pr_status"
SELECTED_VENDOR_KEY = "selected_vendor"
NEGOTIATION_CONFIG_KEY = "negotiation_config"

# Human-applied overrides per vendor thread, keyed by rfq_id.
# Shape: { rfq_id: { "status": "ESCALATED" | "WALKED_AWAY", "reason": str, "ts": iso8601 } }
# Layered on top of NEGOTIATION_CONFIG_KEY at read time so the agent's own
# write path doesn't need to know about them.
VENDOR_THREAD_OVERRIDES_KEY = "vendor_thread_overrides"

# Post-negotiation purchase flow
PO_KEY = "po"
GRN_KEY = "grn"
INVOICE_KEY = "invoice"
PROCESS_COMPLETE_KEY = "process_complete"

# Human-approval gate: True once the AWAITING_USER_APPROVAL summary has been shown,
# allowing the next loop iteration to process the user's approval message.
PO_APPROVAL_SHOWN_KEY = "po_approval_shown"
