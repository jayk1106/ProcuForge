# PR Status Reference

Every Purchase Request (PR) has a single top-level `pr_status` at any given moment. This is a derived value — computed from the underlying agent states — and represents the current overall state of the workflow.

**Total statuses:** 21

---

## Initiation

| Status                   | Meaning                                                                                                                                                                                                 |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `INITIATED`              | PR has just been submitted by the user. Buyer agent is preparing to discover vendors.                                                                                                                   |
| `VENDORS_DISCOVERED`     | Buyer agent has shortlisted candidate vendors for this product. Negotiation has not started yet.                                                                                                      |
| `NO_VENDORS_DISCOVERED` | Vendor discovery finished with **no** shortlisted vendors for this product (empty discovery result). Negotiation does not start. Not the same as `NO_VENDOR_AVAILABLE`, which applies after negotiation when every vendor has walked away. |

## Negotiation

| Status                    | Meaning                                                                                                         |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `NEGOTIATION_IN_PROGRESS` | One or more vendor negotiations are actively running. Vendors may be at different rounds.                       |
| `NEGOTIATION_COMPLETED`   | All vendor negotiations have finished. Some vendors accepted, some walked away. Decision agent is about to run. |
| `NO_VENDOR_AVAILABLE`     | All vendors walked away from negotiation. No deal is possible for this PR.                                      |

## Vendor Selection

| Status                   | Meaning                                                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| `VENDOR_SELECTED`        | Decision agent has picked a winning vendor. PO generation is queued.                                                         |
| `AWAITING_USER_APPROVAL` | A winning vendor was selected, but the PR requires human approval before the PO is issued (e.g., budget threshold exceeded). |

## Purchase Order

| Status            | Meaning                                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------------------------- |
| `PO_ISSUED`       | PO has been sent to the vendor. Waiting for vendor acknowledgment.                                         |
| `PO_ACKNOWLEDGED` | Vendor has confirmed the PO terms match the negotiated agreement. Deal is locked.                          |
| `PO_REJECTED`     | Vendor rejected the PO due to a mismatch (e.g., price or quantity drift). Needs review or PO regeneration. |

## Delivery

| Status              | Meaning                                                                         |
| ------------------- | ------------------------------------------------------------------------------- |
| `AWAITING_DELIVERY` | PO acknowledged. Waiting for physical goods to arrive at the warehouse.         |
| `GOODS_RECEIVED`    | Goods have arrived. GRN has been created with received and accepted quantities. |

## Invoice & Verification

| Status                       | Meaning                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------- |
| `AWAITING_INVOICE`           | GRN done. Waiting for the vendor to submit an invoice.                                |
| `INVOICE_UNDER_VERIFICATION` | Invoice received. Verification agent is running the 3-way match (PO ↔ GRN ↔ Invoice). |
| `INVOICE_CORRECTION_PENDING` | Verification found discrepancies. Vendor has been asked to send a corrected invoice.  |
| `INVOICE_VERIFIED`           | 3-way match passed. Invoice is approved and ready for the final payment step.         |

## Completion

| Status              | Meaning                                                                                           |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| `READY_FOR_PAYMENT` | Everything verified. Final state before payment. Awaiting human authorization to release payment. |
| `COMPLETED`         | Payment authorized by user. PR is closed. Terminal state.                                         |

## Exceptions

These statuses can occur at any phase and override the normal flow.

| Status      | Meaning                                                                                                                                       |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `ESCALATED` | Something went wrong that the agents cannot resolve (e.g., repeated state mismatches, max correction rounds exceeded). Human review required. |
| `CANCELLED` | User cancelled the PR before it completed. Terminal state.                                                                                    |

---

## Status Transitions

```
INITIATED
  → VENDORS_DISCOVERED
  → NO_VENDORS_DISCOVERED
  → CANCELLED

NO_VENDORS_DISCOVERED
  → CANCELLED
  → ESCALATED                (if human may onboard vendors or correct catalog data)

VENDORS_DISCOVERED
  → NEGOTIATION_IN_PROGRESS
  → CANCELLED

NEGOTIATION_IN_PROGRESS
  → NEGOTIATION_COMPLETED
  → NO_VENDOR_AVAILABLE
  → CANCELLED

NEGOTIATION_COMPLETED
  → VENDOR_SELECTED

VENDOR_SELECTED
  → AWAITING_USER_APPROVAL   (if approval gate triggered)
  → PO_ISSUED                (if no approval needed)

AWAITING_USER_APPROVAL
  → PO_ISSUED
  → CANCELLED

PO_ISSUED
  → PO_ACKNOWLEDGED
  → PO_REJECTED
  → ESCALATED

PO_REJECTED
  → PO_ISSUED                (after fix)
  → ESCALATED
  → CANCELLED

PO_ACKNOWLEDGED
  → AWAITING_DELIVERY

AWAITING_DELIVERY
  → GOODS_RECEIVED

GOODS_RECEIVED
  → AWAITING_INVOICE

AWAITING_INVOICE
  → INVOICE_UNDER_VERIFICATION

INVOICE_UNDER_VERIFICATION
  → INVOICE_VERIFIED
  → INVOICE_CORRECTION_PENDING
  → ESCALATED

INVOICE_CORRECTION_PENDING
  → INVOICE_UNDER_VERIFICATION
  → ESCALATED                (after 3 correction rounds)

INVOICE_VERIFIED
  → READY_FOR_PAYMENT

READY_FOR_PAYMENT
  → COMPLETED

ESCALATED
  → (resolved manually, returns to previous legal status)
  → CANCELLED

NO_VENDOR_AVAILABLE
  → CANCELLED

CANCELLED, COMPLETED → terminal (no transitions out)
```
