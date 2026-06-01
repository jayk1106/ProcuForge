# Buyer Agent — State Management Reference

This document describes every session state key the buyer agent reads and writes,
the full `PrStatus` lifecycle, and frontend display guidance for each status.
Use this as the authoritative reference when building buyer-facing UI logic.

---

## 1. State Keys

All keys live in `procu_forge_buyer/state_keys.py`.

### 1.1 Core Procurement Keys

| State Key | Python Constant | Type | Set By | Description |
|-----------|----------------|------|--------|-------------|
| `pr_status` | `PR_STATUS_KEY` | `str` (PrStatus) | `pr_status_transitions.py` functions | **Primary UI driver.** Current phase of the procurement request. |
| `previous_pr_status` | `PREVIOUS_PR_STATUS_KEY` | `str` (PrStatus) | Same transition functions | Status immediately before current — use for progress indicators and "went back" detection. |
| `request` | `REQUEST_KEY` | `dict` | Initial session seed (external) | The original procurement request from the requester. |
| `vendor_offers` | `VENDOR_OFFERS_KEY` | `dict` | `vendor_search/tools.py → load_vendor_offers_for_product` | All discovered vendor catalog offers for the requested product. |
| `negotiation_config` | `NEGOTIATION_CONFIG_KEY` | `dict[vendor_id → config]` | `negotiator/tools.py → negotiate_with_vendor` | Per-vendor negotiation state. Accumulates each round of messages. |
| `selected_vendor` | `SELECTED_VENDOR_KEY` | `dict` | `decision/tools.py → select_vendor` | The winning vendor chosen by the decision agent. |

### 1.2 Purchase Flow Keys

| State Key | Python Constant | Type | Set By | Description |
|-----------|----------------|------|--------|-------------|
| `po` | `PO_KEY` | `dict` | `purchase_manager/tools.py → send_po` | Outbound Purchase Order sent to the vendor. |
| `grn` | `GRN_KEY` | `dict` | `purchase_manager/tools.py → send_grn_created` | Goods Receipt Note sent to the vendor after delivery. |
| `invoice` | `INVOICE_KEY` | `dict` | `purchase_manager/tools.py → send_grn_created` (populated from vendor reply) | Invoice returned by the vendor in response to the GRN. |
| `process_complete` | `PROCESS_COMPLETE_KEY` | `dict` | `purchase_manager/tools.py → send_process_complete` | Confirmation that the full procurement cycle is closed. |

### 1.3 Internal / Gate Keys

| State Key | Python Constant | Type | Set By | Description | Frontend Use |
|-----------|----------------|------|--------|-------------|-------------|
| `po_approval_shown` | `PO_APPROVAL_SHOWN_KEY` | `bool` | `callbacks.py → stop_loop_if_terminal` | `True` once the approval summary was shown to the human. The loop stops on the first encounter; on the next user message this flag lets the loop continue to call `approve_po`. | Expose as "approval pending" indicator. Do not let the user re-trigger the approval flow if `True`. |

---

## 2. State Key Schemas

### `request`
```json
{
  "product_id": "string",
  "quantity": 10,
  "currency": "USD",
  "required_by_date": "2026-07-01",
  "budget_ceiling": 950.00,
  "urgency": "normal",
  "delivery": "standard",
  "buyer_notes": "string"
}
```
Set externally before the workflow starts. Never mutated by the buyer agents.

---

### `vendor_offers`
```json
{
  "productId": "string",
  "offerCount": 3,
  "offers": [
    {
      "id": "string",
      "vendor_id": "string",
      "product_id": "string",
      "vendor_sku": "string",
      "unit": "each",
      "unit_price": 1000.00,
      "currency": "USD",
      "lead_time_days": 7,
      "contracted": false,
      "availability_status": "IN_STOCK"
    }
  ]
}
```
Set once by `vendor_search_agent`. Read by `negotiator_agent` (to initialise per-vendor config) and `decision_agent` (to show catalog prices).

---

### `negotiation_config` (per vendor entry)
```json
{
  "vendor_id": "string",
  "rfq_id": "uuid-string",
  "round": 2,
  "done": true,
  "target_price": 900.00,
  "product": {
    "id": "string",
    "sku": "string",
    "currency": "USD",
    "unit": "each",
    "price": 1000.00,
    "quantity": 10
  },
  "communications": [
    { "message_type": "RFQ", "round": 0, "payload": { "..." } },
    { "message_type": "QUOTE", "round": 0, "payload": { "unit_price": 950.00 } },
    { "message_type": "COUNTER_OFFER", "round": 1, "payload": { "unit_price": 900.00 } },
    { "message_type": "ACCEPT", "round": 1, "payload": { "unit_price": 900.00 } }
  ]
}
```
`done: true` means this vendor's thread is closed (buyer sent ACCEPT or WALKAWAY).
`communications` alternates buyer-sent (dict) and vendor-replied (dict, parsed from A2A envelope).

**Determining negotiation outcome from `communications`:**
- Find the last entry where `from_agent == "buyer_agent"`
- `message_type == "ACCEPT"` → vendor accepted at `payload.unit_price`
- `message_type == "WALKAWAY"` → buyer walked away; reference price in `payload.last_unit_price`

---

### `selected_vendor`
```json
{
  "vendor": "vendor_id_string",
  "final_price": 900.00,
  "outcome": "ACCEPTED"
}
```
`outcome` is either `"ACCEPTED"` (normal win) or `"WALKED_AWAY"` (all-walkaway fallback — in this case `pr_status` goes to `NO_VENDOR_AVAILABLE`, not to the purchase flow).

---

### `po`
```json
{
  "po_number": "PO-A1B2C3D4",
  "rfq_reference": "uuid-string",
  "line_items": [
    {
      "sku": "string",
      "product_id": "string",
      "quantity": 10,
      "unit_price": 900.00,
      "total_price": 9000.00
    }
  ],
  "total_amount": 9000.00,
  "delivery_date": "2026-07-01",
  "agreed_price": 900.00,
  "vendor_id": "string"
}
```

---

### `grn`
```json
{
  "grn_number": "GRN-E5F6G7H8",
  "po_number": "PO-A1B2C3D4",
  "received_at": "2026-06-15T12:00:00Z",
  "line_items": [
    { "sku": "string", "unit_quantity": 10 }
  ]
}
```

---

### `invoice`
```json
{
  "invoice_number": "INV-rfq_id-ABCD1234",
  "po_number": "PO-A1B2C3D4",
  "invoice_date": "2026-06-15",
  "line_items": [
    {
      "sku": "string",
      "quantity": 10,
      "unit_price": 900.00,
      "total_price": 9000.00
    }
  ],
  "total_amount": 9000.00,
  "grn_reference": "GRN-E5F6G7H8",
  "due_date": "2026-07-15"
}
```

---

### `process_complete`
```json
{
  "po_number": "PO-A1B2C3D4",
  "grn_number": "GRN-E5F6G7H8",
  "invoice_number": "INV-rfq_id-ABCD1234"
}
```

---

## 3. PrStatus Lifecycle

Defined in `procu_forge_buyer/pr_status.py`. Transitions live in `procu_forge_buyer/pr_status_transitions.py`.

### 3.1 State Machine

```
INITIATED
  │ [auto] vendor_search discovers ≥1 offer
  ├──→ VENDORS_DISCOVERED
  │     │ [auto] negotiator_agent starts first turn
  │     └──→ NEGOTIATION_IN_PROGRESS
  │               │ [auto] every targeted vendor has done=True
  │               └──→ NEGOTIATION_COMPLETED
  │                         │ [auto] ≥1 vendor ACCEPTED → decision selects winner
  │                         ├──→ VENDOR_SELECTED
  │                         │         │ [auto] RFQ_CLOSED sent to losing vendors
  │                         │         └──→ AWAITING_USER_APPROVAL  ← HUMAN GATE
  │                         │                   │ [human] user sends approval message
  │                         │                   └──→ PO_ISSUED
  │                         │                             │ [auto] vendor sends PO_ACKNOWLEDGED
  │                         │                             └──→ PO_ACKNOWLEDGED
  │                         │                                       │ [auto] GRN sent + invoice received
  │                         │                                       └──→ INVOICE_UNDER_VERIFICATION
  │                         │                                                 │ [auto] PROCESS_COMPLETE sent
  │                         │                                                 └──→ COMPLETED ✓
  │                         │
  │                         └─ [auto] all vendors walked away
  │                               └──→ NO_VENDOR_AVAILABLE ✗
  │
  └── [auto] no offers found
        └──→ NO_VENDORS_DISCOVERED ✗

--- Interruption / future states (set externally or via future agents) ---
PO_REJECTED          — vendor rejected the PO
AWAITING_DELIVERY    — PO acknowledged, waiting for goods
GOODS_RECEIVED       — goods arrived, GRN pending
AWAITING_INVOICE     — GRN sent, waiting for invoice
INVOICE_CORRECTION_PENDING — invoice had errors, vendor must correct
INVOICE_VERIFIED     — invoice approved, payment queued
READY_FOR_PAYMENT    — payment authorisation needed
ESCALATED            — requires human escalation
CANCELLED            — PR cancelled
```

### 3.2 Transition Functions Reference

| Transition | Function | Source → Target |
|-----------|----------|----------------|
| Offers found / not found | `transition_after_vendor_discovery(state, offer_count)` | INITIATED → VENDORS_DISCOVERED or NO_VENDORS_DISCOVERED |
| Negotiation starts | `transition_to_negotiation_in_progress(state)` | VENDORS_DISCOVERED → NEGOTIATION_IN_PROGRESS |
| All vendors done | `transition_after_negotiation(state)` | NEGOTIATION_IN_PROGRESS → NEGOTIATION_COMPLETED |
| Vendor selected | `transition_after_decision(state)` | NEGOTIATION_COMPLETED → VENDOR_SELECTED |
| Human review | `transition_to_awaiting_user_approval(state)` | VENDOR_SELECTED → AWAITING_USER_APPROVAL |
| Human approved | `transition_to_po_issued(state)` | AWAITING_USER_APPROVAL → PO_ISSUED |
| PO acknowledged | `transition_to_po_acknowledged(state)` | PO_ISSUED → PO_ACKNOWLEDGED |
| Invoice received | `transition_to_invoice_under_verification(state)` | PO_ACKNOWLEDGED → INVOICE_UNDER_VERIFICATION |
| Cycle complete | `transition_to_completed(state)` | INVOICE_UNDER_VERIFICATION → COMPLETED |

### 3.3 Stop Categories

Defined in `pr_status_transitions.py`:

```python
TERMINAL_PR_STATUSES = {COMPLETED, CANCELLED, NO_VENDORS_DISCOVERED, NO_VENDOR_AVAILABLE}

HUMAN_GATED_PR_STATUSES = {
    ESCALATED, AWAITING_USER_APPROVAL, READY_FOR_PAYMENT,
    AWAITING_DELIVERY, GOODS_RECEIVED, AWAITING_INVOICE,
    INVOICE_CORRECTION_PENDING, INVOICE_VERIFIED, PO_REJECTED
}

STOP_PR_STATUSES = TERMINAL_PR_STATUSES | HUMAN_GATED_PR_STATUSES
```

> **Note on AWAITING_USER_APPROVAL:** The agent loop stops on the **first** encounter
> (to display the selection summary). When the user sends the next message, the loop
> restarts and `po_approval_shown=True` prevents a second stop — the loop proceeds
> to call `approve_po` and advance to `PO_ISSUED`.

---

## 4. Data Available Per Status

The table below shows which state keys are guaranteed to be populated at each status.
Use this to know which UI sections to render.

| pr_status | `request` | `vendor_offers` | `negotiation_config` | `selected_vendor` | `po` | `grn` | `invoice` | `process_complete` |
|-----------|:---------:|:---------------:|:--------------------:|:-----------------:|:----:|:-----:|:---------:|:-----------------:|
| INITIATED | ✓ | — | — | — | — | — | — | — |
| VENDORS_DISCOVERED | ✓ | ✓ | — | — | — | — | — | — |
| NEGOTIATION_IN_PROGRESS | ✓ | ✓ | partial | — | — | — | — | — |
| NEGOTIATION_COMPLETED | ✓ | ✓ | ✓ (all done) | — | — | — | — | — |
| VENDOR_SELECTED | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| AWAITING_USER_APPROVAL | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| PO_ISSUED | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — |
| PO_ACKNOWLEDGED | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — |
| INVOICE_UNDER_VERIFICATION | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| COMPLETED | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| NO_VENDORS_DISCOVERED | ✓ | ✓ (empty) | — | — | — | — | — | — |
| NO_VENDOR_AVAILABLE | ✓ | ✓ | ✓ | ✓ (outcome=WALKED_AWAY) | — | — | — | — |

> `negotiation_config` is "partial" during NEGOTIATION_IN_PROGRESS — some vendor
> threads may have `done=false` and incomplete communications.

---

## 5. Human Gate — AWAITING_USER_APPROVAL

This is the only status requiring explicit human input before the workflow continues.

| Field | Value |
|-------|-------|
| **Status** | `AWAITING_USER_APPROVAL` |
| **What to show** | Selected vendor card: `selected_vendor.vendor`, `selected_vendor.final_price`, `selected_vendor.outcome`; comparison against `vendor_offers` |
| **Required action** | User sends any follow-up message (treated as approval) |
| **What happens next** | `approve_po` tool is called → `pr_status = PO_ISSUED` → `send_po` runs on next turn |
| **Cancel path** | Not yet automated — set `pr_status = CANCELLED` externally via API |
| **Gate flag** | `po_approval_shown` — `True` means the summary was already displayed once |

**Recommended UI:**
- Show a prominent "Approve PO" button that sends a message to the agent (e.g., "Approved — proceed with PO issuance").
- Show vendor summary: vendor name, agreed price, original catalog price, discount achieved.
- Show "Cancel" button that calls an external API to set `pr_status = CANCELLED`.

---

## 6. Frontend Status Categories

Use these categories to determine which UI component to render for a given `pr_status`.

| Category | Statuses | Suggested Treatment |
|----------|----------|-------------------|
| **Processing (auto)** | `INITIATED`, `VENDORS_DISCOVERED`, `NEGOTIATION_IN_PROGRESS`, `NEGOTIATION_COMPLETED`, `VENDOR_SELECTED` | Spinner / progress stepper — no action needed |
| **Human gate** | `AWAITING_USER_APPROVAL` | Action card with Approve / Cancel buttons |
| **Document flow (auto)** | `PO_ISSUED`, `PO_ACKNOWLEDGED`, `INVOICE_UNDER_VERIFICATION` | Document timeline — PO → GRN → Invoice |
| **Success** | `COMPLETED` | Green success banner with summary |
| **No vendor** | `NO_VENDORS_DISCOVERED`, `NO_VENDOR_AVAILABLE` | Red error state with retry option |
| **Blocked / interrupted** | `PO_REJECTED`, `ESCALATED`, `CANCELLED` | Alert banner with manual action needed |
| **External trigger awaited** | `AWAITING_DELIVERY`, `GOODS_RECEIVED`, `AWAITING_INVOICE`, `INVOICE_CORRECTION_PENDING`, `INVOICE_VERIFIED`, `READY_FOR_PAYMENT` | Waiting state — action required outside this system |

---

## 7. Negotiation Config — Rendering a Timeline

To display the negotiation history for a vendor, iterate `negotiation_config[vendor_id].communications`:

```
Index 0   — buyer sends RFQ           (from_agent: buyer_agent,  message_type: RFQ)
Index 1   — vendor sends QUOTE        (from_agent: vendor_agent, message_type: QUOTE)
Index 2   — buyer sends COUNTER_OFFER (from_agent: buyer_agent,  message_type: COUNTER_OFFER)
Index 3   — vendor sends COUNTER_OFFER(from_agent: vendor_agent, message_type: COUNTER_OFFER)
...
Index N-1 — buyer sends ACCEPT        (from_agent: buyer_agent,  message_type: ACCEPT)
Index N   — vendor sends ACCEPT       (from_agent: vendor_agent, message_type: ACCEPT)
```

**Key fields per entry:**
- `message_type` — `RFQ | QUOTE | COUNTER_OFFER | ACCEPT | WALKAWAY`
- `from_agent` — `"buyer_agent"` or `"vendor_agent"`
- `round` — integer, matching round on both sides
- `timestamp` — ISO-8601 UTC
- `payload.unit_price` — price offered this round (QUOTE, COUNTER_OFFER, ACCEPT)
- `payload.is_final` — `true` if vendor marked this as best-and-final

**Determining final outcome:**
```
last_buyer_message = last entry where from_agent == "buyer_agent"
if last_buyer_message.message_type == "ACCEPT":
    outcome = "ACCEPTED", price = last_buyer_message.payload.unit_price
elif last_buyer_message.message_type == "WALKAWAY":
    outcome = "WALKED_AWAY"
```
