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

# Vendor-confirmed milestones (required before pr_status advances past each step)
PO_VENDOR_ACK_KEY = "po_vendor_ack"
INVOICE_VENDOR_ACK_KEY = "invoice_vendor_ack"
PROCESS_COMPLETE_VENDOR_ACK_KEY = "process_complete_vendor_ack"

# Human-in-the-loop approval policy (set at workflow start).
# When True, purchase_manager pauses before each of PO / GRN / PROCESS_COMPLETE
# until the matching step appears in APPROVED_STEPS_KEY.
APPROVAL_REQUIRED_KEY = "approval_required"
# Steps the human has signed off on. Values: "po" | "grn" | "completion".
APPROVED_STEPS_KEY = "approved_steps"
# Block describing the gate the workflow is currently parked at.
# Shape: { "step": "po"|"grn"|"completion", "reason": str, "requested_at": iso8601 }
PENDING_APPROVAL_KEY = "pending_approval"

# Losing vendors notified with RFQ_CLOSED (vendor_id -> True); idempotent send guard
RFQ_CLOSED_LOSERS_KEY = "rfq_closed_losers"

# Purchase stall detection: snapshot at start of each purchase_manager turn
PURCHASE_STEP_SNAPSHOT_KEY = "purchase_step_snapshot"
PURCHASE_STALL_STREAK_KEY = "purchase_stall_streak"

# Negotiator stall detection: snapshot of per-vendor communications lengths taken at
# the start of each negotiator turn; compared in the after-callback to detect no-progress turns.
NEGOTIATOR_COMMS_SNAPSHOT_KEY = "negotiator_comms_snapshot"
# Count of consecutive negotiator turns that produced no new communications.
# Resets to 0 on any turn that makes progress. Used for the stall-guard force-close.
NEGOTIATOR_STALL_STREAK_KEY = "negotiator_stall_streak"

# Escalation notification (written by buyer agent; email sent by API layer)
ESCALATION_CONTEXT_KEY = "escalation_context"
ESCALATION_PENDING_NOTIFY_KEY = "escalation_pending_notify"
ESCALATION_EMAIL_SENT_AT_KEY = "escalation_email_sent_at"
INVOICE_CORRECTION_ROUNDS_KEY = "invoice_correction_rounds"
PO_REJECTION_COUNT_KEY = "po_rejection_count"
LOOP_ITERATION_KEY = "loop_iteration"
