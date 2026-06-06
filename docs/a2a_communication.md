# Procurement Agent Communication Reference

Human-readable companion to `schema/communication.json`. Use this when designing flows, debugging, or onboarding teammates. The JSON Schema file is the source of truth for validation.

**Schema version:** `1.0.0`

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          BUYER SIDE                                 │
│                                                                     │
│  Negotiator → Decision → PO → GRN → Verification → User            │
│      ↑           ↓        ↓     ↓         ↓                        │
│      ↓           ↓        ↓     ↓         ↓                        │
└──────┼───────────┼────────┼─────┼─────────┼────────────────────────┘
       ↓           ↓        ↓     ↓         ↑
┌──────┼───────────┼────────┼─────┼─────────┼────────────────────────┐
│      ↓           ↓        ↓     ↓         ↓                        │
│                    VENDOR AGENT (single, vendor_id-aware)          │
└─────────────────────────────────────────────────────────────────────┘
```

The vendor agent is **single-instance, multi-tenant**. Every inbound message carries a `vendor_id` so the agent can load the right pricing/config. The buyer side has multiple specialized agents, each owning one phase.

---

## Message envelope

Every message — regardless of type — uses the same envelope. The `payload` shape varies by `message_type`.

```json
{
  "schema_version": "1.0.0",
  "message_id": "msg_a1b2c3d4",
  "rfq_id": "rfq_2026_0001",
  "vendor_id": "vendor_123",
  "from_agent": "buyer_negotiator",
  "to_agent": "vendor",
  "message_type": "RFQ",
  "round": 0,
  "timestamp": "2026-05-09T10:30:00Z",
  "payload": { ... }
}
```

**Key envelope rules:**

- `rfq_id` threads the **entire transaction** end-to-end. Every message from RFQ to `PROCESS_COMPLETE` carries the same `rfq_id`.
- `message_id` is **unique per message**. Used for idempotency — if a duplicate arrives, the receiver discards it.
- `vendor_id` is **always present**, even on internal buyer-side messages, so the transaction stays traceable. For `VENDOR_SELECTED` use the selected vendor's id.
- `round` is `0` for RFQ, `1-3` for negotiation messages, `null` (or omitted) for everything post-negotiation. The schema does not enforce this conditional; agents should set it correctly.
- `from_agent` / `to_agent` are restricted to the agent enum, plus `user` and `buyer_system` (only valid as the `to_agent` of `PROCESS_COMPLETE`).

---

## Phases


| Phase                     | Agents involved                            | Purpose                              |
| ------------------------- | ------------------------------------------ | ------------------------------------ |
| 1. Negotiation            | buyer_negotiator ↔ vendor                  | Establish a price                    |
| 2. Vendor Selection       | buyer_decision → buyer_po, vendor (losers) | Pick a winner, notify losers         |
| 3. PO                     | buyer_po ↔ vendor                          | Issue and acknowledge purchase order |
| 4. GRN                    | buyer_grn → vendor + buyer_verification    | Record physical receipt              |
| 5. Invoice & Verification | vendor ↔ buyer_verification                | 3-way match and corrections          |
| 6. Completion             | buyer_verification → user                  | Hand off to human for payment        |


---

# Phase 1: Negotiation

Run independently with **each vendor**. Capped at **3 rounds**. Buyer agent decides autonomously based on rule-based logic.

## RFQ

**Direction:** `buyer_negotiator → vendor`
**When:** Start of transaction. One per vendor being solicited.

```json
{
  "schema_version": "1.0.0",
  "message_id": "msg_rfq_001",
  "rfq_id": "rfq_2026_0001",
  "vendor_id": "vendor_123",
  "from_agent": "buyer_negotiator",
  "to_agent": "vendor",
  "message_type": "RFQ",
  "round": 0,
  "timestamp": "2026-05-09T10:00:00Z",
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

## QUOTE

**Direction:** `vendor → buyer_negotiator`
**When:** In response to RFQ. Round 1.

```json
{
  "payload": {
    "product_id": "prod_widget_a",
    "sku": "ITEM-001",
    "unit_price": 50.0,
    "total_price": 5000.0,
    "currency": "USD",
    "valid_until": "2026-05-16T23:59:59Z",
    "notes": "Standard pricing for 100 units"
  }
}
```

## COUNTER_OFFER

**Direction:** `buyer_negotiator → vendor`
**When:** Quote exceeds buyer's target price.

**Buyer's rule:** `counter_price = max(target_price, vendor_price * 0.92)`

```json
{
  "payload": {
    "product_id": "prod_widget_a",
    "sku": "ITEM-001",
    "proposed_unit_price": 45.0,
    "proposed_total_price": 4500.0,
    "currency": "USD",
    "justification": "Target budget constraint"
  }
}
```

## COUNTER_RESPONSE

**Direction:** `vendor → buyer_negotiator`
**When:** In response to a counter-offer.

The `decision` field carries the vendor's stance:

- `COUNTER` → new price, somewhere between buyer's offer and last quote
- `HOLD` → vendor stands by previous price (`unit_price` / `total_price` repeat the last quote). Buyer can either send another `COUNTER_OFFER` (counts toward the 3-round cap), `ACCEPT`, or `WALKAWAY`.
- `REJECT` → vendor walks away, `is_final: true`. The `unit_price` / `total_price` fields are required by the schema; vendors should repeat their last quoted price (the value is informational only — buyer should treat the negotiation as terminated and emit a `WALKAWAY` if they haven't already).

```json
{
  "payload": {
    "product_id": "prod_widget_a",
    "sku": "ITEM-001",
    "decision": "COUNTER",
    "unit_price": 47.0,
    "total_price": 4700.0,
    "currency": "USD",
    "is_final": false,
    "notes": "Best we can do at this volume"
  }
}
```

## ACCEPT

**Direction:** `buyer_negotiator → vendor`
**When:** Buyer accepts the current price. Locks the deal pending vendor selection.

```json
{
  "payload": {
    "product_id": "prod_widget_a",
    "sku": "ITEM-001",
    "agreed_unit_price": 47.0,
    "agreed_total_price": 4700.0,
    "currency": "USD",
    "quantity": 100
  }
}
```

## WALKAWAY

**Direction:** Either side
**When:** No deal possible. Sent by buyer when max rounds reached and price still unacceptable, or by vendor when buyer's offer is below floor.

```json
{
  "payload": {
    "product_id": "prod_widget_a",
    "sku": "ITEM-001",
    "reason": "MAX_ROUNDS_REACHED",
    "last_offer": 47.0,
    "last_counter": 45.0
  }
}
```

### Negotiation state diagram

```
RFQ_SENT ──→ QUOTE_RECEIVED
                  │
        ┌─────────┴──────────┐
        ↓                    ↓
   price ≤ target      price > target
        ↓                    ↓
    ACCEPTED         COUNTER_OFFER ──→ COUNTER_RESPONSE
                          ↑                 │
                          │   ┌─────────────┼─────────────┐
                          │   ↓             ↓             ↓
                          │ COUNTER       HOLD         REJECT
                          │   │             │             ↓
                          │   │             │          WALKAWAY
                          │   └──────┬──────┘
                          │          ↓
                          │   buyer decides:
                          └── COUNTER_OFFER (if round < 3)
                              ACCEPT          (any round)
                              WALKAWAY        (if round = 3
                                               and price > target)
```

Both `COUNTER` and `HOLD` loop back to the buyer's decision point. The buyer keeps a per-`rfq_id` round counter and stops when it hits 3.

---

# Phase 2: Vendor Selection

Triggered after all parallel negotiations finish (some `ACCEPTED`, some `WALKAWAY`).

## VENDOR_SELECTED

**Direction:** `buyer_decision → buyer_po` (internal)
**When:** Decision agent picks the winner. Hands off to PO agent.

> **Envelope convention:** even though this is an internal handoff, the envelope still requires `vendor_id`. Set it to the **selected** vendor's id (same value as `payload.selected_vendor_id`). This keeps every message in the transaction filterable by `vendor_id`.

```json
{
  "from_agent": "buyer_decision",
  "to_agent": "buyer_po",
  "vendor_id": "vendor_123",
  "message_type": "VENDOR_SELECTED",
  "payload": {
    "selected_vendor_id": "vendor_123",
    "selected_quote_amount": 4700.0,
    "currency": "USD",
    "selection_criteria": "LOWEST_PRICE",
    "evaluated_vendors": [
      { "vendor_id": "vendor_123", "final_price": 4700.0, "rank": 1 },
      { "vendor_id": "vendor_456", "final_price": 4850.0, "rank": 2 },
      { "vendor_id": "vendor_789", "final_price": 5000.0, "rank": 3 }
    ]
  }
}
```

## RFQ_CLOSED

**Direction:** `buyer_decision → vendor` (one per losing vendor)
**When:** Right after `VENDOR_SELECTED`. Critical — without it, losing vendors stay in `ACCEPTED` state forever.

```json
{
  "vendor_id": "vendor_456",
  "message_type": "RFQ_CLOSED",
  "payload": {
    "outcome": "NOT_SELECTED",
    "reason": "ANOTHER_VENDOR_SELECTED",
    "closed_at": "2026-05-12T09:00:00Z"
  }
}
```

---

# Phase 3: PO

Two-step handshake. PO is not "active" until vendor acknowledges.

## PO

**Direction:** `buyer_po → vendor`
**When:** Right after vendor selection.

```json
{
  "payload": {
    "po_number": "PO-2026-0042",
    "rfq_reference": "rfq_2026_0001",
    "line_items": [
      {
        "sku": "ITEM-001",
        "description": "Industrial widget, grade A",
        "quantity": 100,
        "unit_price": 47.0,
        "line_total": 4700.0
      }
    ],
    "total_amount": 4700.0,
    "currency": "USD",
    "delivery_date": "2026-06-15",
    "issued_at": "2026-05-12T10:00:00Z"
  }
}
```

## PO_ACKNOWLEDGED

**Direction:** `vendor → buyer_po`
**When:** Vendor agent validates PO matches negotiated agreement.

**Why this matters:** vendor agent checks that PO `total_amount` equals the `agreed_total_price` from the `ACCEPT` message. If buyer-side has a bug (wrong price written into PO), this catches it.

```json
{
  "payload": {
    "po_number": "PO-2026-0042",
    "status": "ACKNOWLEDGED",
    "expected_delivery_date": "2026-06-15",
    "rejection_reason": null,
    "acknowledged_at": "2026-05-12T10:30:00Z"
  }
}
```

If status is `REJECTED`, the `rejection_reason` describes the mismatch (e.g., `"PRICE_MISMATCH: PO shows $48, agreed $47"`) and the buyer side must regenerate the PO or escalate.

---

# Phase 4: GRN

Fired when goods physically arrive at the buyer's warehouse. **Buyer-side only** — vendor agent does not write GRNs.

## GRN_CREATED

**Direction:** `buyer_grn → vendor` + `buyer_grn → buyer_verification`
**When:** Goods received and QC done.

The `accepted_quantity` (not `received_quantity`) feeds into the 3-way match — accounts for damaged or rejected items.

```json
{
  "payload": {
    "grn_number": "GRN-2026-0089",
    "po_number": "PO-2026-0042",
    "received_at": "2026-06-14T14:30:00Z",
    "received_by": "warehouse_user_42",
    "line_items": [
      {
        "sku": "ITEM-001",
        "ordered_quantity": 100,
        "received_quantity": 100,
        "accepted_quantity": 98,
        "rejected_quantity": 2,
        "rejection_reason": "DAMAGED"
      }
    ],
    "status": "PARTIAL"
  }
}
```

`status` values:

- `COMPLETE` → ordered = received = accepted
- `PARTIAL` → some items short or rejected, but transaction can proceed
- `DISCREPANCY` → significant variance, may need escalation

---

# Phase 5: Invoice & Verification

The 3-way match: PO ↔ GRN ↔ Invoice. Capped at **3 correction rounds**.

## INVOICE_SUBMITTED

**Direction:** `vendor → buyer_verification`
**When:** Vendor sends invoice. Triggered after vendor receives `GRN_CREATED` (so they know what was accepted).

```json
{
  "payload": {
    "invoice_number": "INV-V123-2026-0017",
    "po_number": "PO-2026-0042",
    "grn_reference": "GRN-2026-0089",
    "invoice_date": "2026-06-15",
    "line_items": [
      {
        "sku": "ITEM-001",
        "quantity": 100,
        "unit_price": 47.0,
        "line_total": 4700.0
      }
    ],
    "subtotal": 4700.0,
    "tax": 846.0,
    "total_amount": 5546.0,
    "currency": "USD",
    "payment_terms": "NET_30",
    "due_date": "2026-07-15"
  }
}
```

In this example the vendor billed for the full ordered quantity (100), but the GRN only accepted 98. The 3-way match below catches that and the vendor resubmits a corrected invoice.

## INVOICE_VERIFICATION_RESULT

**Direction:** `buyer_verification → vendor`
**When:** After 3-way match runs.

The `checks` object reports each individual match. The `discrepancies` array lists what's wrong, scoped to the field level. `next_action` tells the vendor agent what to do next.

```json
{
  "payload": {
    "invoice_number": "INV-V123-2026-0017",
    "po_number": "PO-2026-0042",
    "grn_reference": "GRN-2026-0089",
    "status": "REJECTED",
    "verification_round": 1,
    "max_correction_rounds": 3,
    "checks": {
      "po_match": "PASS",
      "grn_match": "FAIL",
      "price_match": "PASS",
      "quantity_match": "FAIL",
      "tax_calculation": "PASS"
    },
    "discrepancies": [
      {
        "field": "quantity",
        "expected": 98,
        "received_in_invoice": 100,
        "source": "GRN",
        "severity": "BLOCKING"
      }
    ],
    "next_action": "RESUBMIT_CORRECTED_INVOICE",
    "verified_at": "2026-06-16T09:00:00Z"
  }
}
```

### Status semantics


| Status                    | Meaning                                           | next_action                  |
| ------------------------- | ------------------------------------------------- | ---------------------------- |
| `APPROVED`                | Clean match                                       | `PROCEED_TO_PAYMENT`         |
| `APPROVED_WITH_TOLERANCE` | Minor variance within tolerance (e.g., ±2% price) | `PROCEED_TO_PAYMENT`         |
| `REJECTED` (round < 3)    | Blocking discrepancy, can retry                   | `RESUBMIT_CORRECTED_INVOICE` |
| `REJECTED` (round = 3)    | Max rounds hit                                    | `ESCALATE_TO_HUMAN`          |


## INVOICE_CORRECTED

**Direction:** `vendor → buyer_verification`
**When:** In response to a `REJECTED` verification result.

The `corrections_made` array makes the diff explicit — useful for debugging and audits.

```json
{
  "payload": {
    "original_invoice_number": "INV-V123-2026-0017",
    "corrected_invoice_number": "INV-V123-2026-0017-R1",
    "correction_round": 1,
    "po_number": "PO-2026-0042",
    "grn_reference": "GRN-2026-0089",
    "corrections_made": [
      {
        "field": "quantity",
        "old_value": 100,
        "new_value": 98
      },
      {
        "field": "line_total",
        "old_value": 4700.0,
        "new_value": 4606.0
      },
      {
        "field": "subtotal",
        "old_value": 4700.0,
        "new_value": 4606.0
      },
      {
        "field": "tax",
        "old_value": 846.0,
        "new_value": 829.08
      },
      {
        "field": "total_amount",
        "old_value": 5546.0,
        "new_value": 5435.08
      }
    ],
    "line_items": [
      {
        "sku": "ITEM-001",
        "quantity": 98,
        "unit_price": 47.0,
        "line_total": 4606.0
      }
    ],
    "subtotal": 4606.0,
    "tax": 829.08,
    "total_amount": 5435.08,
    "currency": "USD"
  }
}
```

The verification agent re-runs the 3-way match and emits another `INVOICE_VERIFICATION_RESULT`. Loop continues up to 3 rounds.

---

# Phase 6: Completion

## PROCESS_COMPLETE

**Direction:** `buyer_verification → user/buyer_system`
**When:** Verification approved, OR escalated, OR closed without deal.

This is the final message in the chain. It prompts a human to authorize payment (or review an escalation).

```json
{
  "payload": {
    "po_number": "PO-2026-0042",
    "grn_number": "GRN-2026-0089",
    "invoice_number": "INV-V123-2026-0017-R1",
    "final_amount": 5435.08,
    "currency": "USD",
    "payment_due_date": "2026-07-15",
    "status": "READY_FOR_PAYMENT",
    "summary": {
      "negotiation_rounds": 2,
      "invoice_correction_rounds": 1,
      "total_cycle_time_days": 38
    },
    "user_action_required": "APPROVE_PAYMENT"
  }
}
```

---

## End-to-end happy path

```
buyer_negotiator ───RFQ──────────────→ vendor
buyer_negotiator ←──QUOTE────────────── vendor
buyer_negotiator ───COUNTER_OFFER────→ vendor
buyer_negotiator ←──COUNTER_RESPONSE── vendor
buyer_negotiator ───ACCEPT───────────→ vendor

buyer_decision   ───VENDOR_SELECTED──→ buyer_po (internal)
buyer_decision   ───RFQ_CLOSED───────→ vendor (losing vendors)

buyer_po         ───PO────────────────→ vendor
buyer_po         ←──PO_ACKNOWLEDGED─── vendor

         (goods physically delivered)

buyer_grn        ───GRN_CREATED──────→ vendor + buyer_verification

vendor           ───INVOICE_SUBMITTED──→ buyer_verification
buyer_verification←─INVOICE_VERIFICATION_RESULT─→ vendor (status: APPROVED)

buyer_verification───PROCESS_COMPLETE→ user
```

---

## Implementation notes

**Validation.** Validate every inbound message against `schema/communication.json` at the agent boundary. Use a JSON Schema library (`ajv` for Node, `jsonschema` for Python). The file is a *bundle*: it contains the envelope schema (top-level `properties` + `required`) plus per-`message_type` payload schemas under `messages.<TYPE>.payload_schema`. Validate envelope first, then dispatch to the matching payload schema. Reject malformed messages with a structured error before they reach business logic.

**Idempotency.** Receivers must dedupe on `message_id`. Store seen IDs for at least 24 hours. Without this, network retries cause double-processing.

**State per `rfq_id`.** Each agent maintains its own state machine keyed on `rfq_id`. Don't trust round numbers from the other side — verify against your own count.

**Event log.** Append every message (in + out) to a per-`rfq_id` log. Even a JSON file works for prototype. Critical for debugging async flows.

**Schema versioning.** Every envelope carries `schema_version`. When you bump it (`1.0.0` → `1.1.0`), agents can warn or reject incompatible versions cleanly.

**Tolerances.** The `APPROVED_WITH_TOLERANCE` status is for variance below a threshold (e.g., price differs by < 2%). Document your tolerance rules even if hardcoded — your future self will need them.

**Correction round cap.** 3 rounds for negotiation, 3 for invoice corrections. Both should escalate to human when hit, not loop forever.

---

## Enum reference

The walkthroughs above only show the most common enum values. The full set defined in `schema/communication.json`:

| Enum | Values |
| ---- | ------ |
| `from_agent` / `to_agent` | `buyer_negotiator`, `buyer_decision`, `buyer_po`, `buyer_grn`, `buyer_verification`, `vendor`, `user` (*to_agent only*), `buyer_system` (*to_agent only*) |
| `walkaway_reason` | `PRICE_GAP_TOO_LARGE`, `MAX_ROUNDS_REACHED`, `VENDOR_REJECTED`, `BUYER_CANCELLED`, `QUOTE_EXPIRED` |
| `rfq_close_reason` | `ANOTHER_VENDOR_SELECTED`, `RFQ_CANCELLED`, `NO_SUITABLE_VENDOR` |
| `RFQ_CLOSED.outcome` | `NOT_SELECTED`, `CANCELLED` |
| `selection_criteria` | `LOWEST_PRICE`, `BEST_VALUE`, `FASTEST_DELIVERY`, `PREFERRED_VENDOR`, `MANUAL_OVERRIDE` |
| `po_ack_status` | `ACKNOWLEDGED`, `REJECTED` |
| `grn_status` | `COMPLETE`, `PARTIAL`, `DISCREPANCY` |
| `GRN line.rejection_reason` | `DAMAGED`, `QUALITY_ISSUE`, `WRONG_ITEM`, `EXPIRED`, `null` |
| `payment_terms` | `NET_15`, `NET_30`, `NET_45`, `NET_60`, `DUE_ON_RECEIPT` |
| `verification_status` | `APPROVED`, `APPROVED_WITH_TOLERANCE`, `REJECTED` |
| `verification_check_result` | `PASS`, `FAIL`, `WARNING` |
| `verification_next_action` | `PROCEED_TO_PAYMENT`, `RESUBMIT_CORRECTED_INVOICE`, `ESCALATE_TO_HUMAN` |
| `discrepancy.severity` | `BLOCKING`, `WARNING` |
| `discrepancy.source` | `PO`, `GRN` |
| `PROCESS_COMPLETE.status` | `READY_FOR_PAYMENT`, `ESCALATED`, `CLOSED_NO_DEAL` |
| `user_action_required` | `APPROVE_PAYMENT`, `REVIEW_ESCALATION`, `ACKNOWLEDGE_NO_DEAL` |
| `currency` | `USD`, `EUR`, `GBP`, `INR`, `JPY`, `CNY`, `AUD`, `CAD` |