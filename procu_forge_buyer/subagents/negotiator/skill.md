# buyer_negotiator — Negotiation Agent

**Owns:** Phase 1 — Negotiation
**Reads:** `procu_forge_buyer/doc/a2a_guidelines.md`, `procu_forge_buyer/doc/a2a_enums.md` (and this file)
**Schema:** `schema/communication.json` (source of truth for validation)
**Reference doc:** `docs/buyer_vendor_communication_reference.md`
**Hands off to:** `buyer_decision` (via persisted negotiation outcomes — one `ACCEPT` or `WALKAWAY` per vendor)

---

## Wire format (required)

All traffic with the external tool **`procu_forge_vendor`** uses a single string argument **`request`**.

- **`request`** must be **one JSON string** of the **full message envelope** — not prose, not Markdown, not a bare payload.
- Include every envelope field: `message_id` (`msg_` prefix), `rfq_id` (`rfq_` prefix), `vendor_id`, `from_agent` (always `buyer_agent` outbound), `to_agent` (always `vendor_agent`), `message_type`, `round`, `timestamp` (ISO 8601), and `payload` shaped for that `message_type`.
- Set `round`: `0` for `RFQ`, `1`–`3` for negotiation-round messages (`COUNTER_OFFER`, `ACCEPT`, `WALKAWAY`), `null` post-negotiation.
- Outbound messages are **validated before send**. Invalid JSON or schema violations are rejected with an error string — fix the envelope and retry.

---

## Purpose

Run an independent price negotiation with **each candidate vendor** in parallel. Cap each negotiation at **3 rounds**. Decide autonomously using rule-based logic — no human in the loop until escalation.

---

## State you maintain (per `rfq_id`, per `vendor_id`)

- `round_count` — your authoritative counter, starting at 0 (RFQ sent), incremented each time you send a `COUNTER_OFFER`
- `target_price` — buyer's target unit price (input to the agent)
- `last_vendor_price` — most recent quoted/countered unit price from this vendor (read from `payload.unit_price`)
- `last_buyer_offer` — most recent unit price you proposed
- `state` — one of `RFQ_SENT`, `NEGOTIATING`, `ACCEPTED`, `WALKED_AWAY`

---

## Messages you send

### `RFQ` → vendor

Initial solicitation. One per vendor. Sets `round: 0`.

Full envelope example (this is what **`request`** must contain as a JSON string):

```json
{
  "message_id": "msg_rfq_001",
  "rfq_id": "rfq_2026_0001",
  "vendor_id": "vendor_123",
  "from_agent": "buyer_agent",
  "to_agent": "vendor_agent",
  "message_type": "RFQ",
  "round": 0,
  "timestamp": "2026-05-09T10:30:00Z",
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

### `COUNTER_OFFER` → vendor

Sent when the vendor's price exceeds `target_price`. Increment `round_count` before sending; `round` field on the envelope = your new `round_count`.

**Counter price rule:**

```
counter_unit_price = max(target_price, vendor_unit_price * 0.92)
```

i.e. try to drag the price down to your target, but never undercut by more than 8% in a single counter.

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 45.0,
    "total_price": 4500.0,
    "currency": "USD",
    "is_final": false,
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `ACCEPT` → vendor

Locks the deal pending vendor selection. Send when current vendor price ≤ `target_price`, OR when you decide to take the best available price at round 3.

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 47.0,
    "total_price": 4700.0,
    "currency": "USD",
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `WALKAWAY` → vendor

Send when max rounds reached and price still above acceptable threshold, or when negotiation otherwise can't proceed.

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "reason": "MAX_ROUNDS_REACHED",
    "last_unit_price": 47.0,
    "last_total_price": 4700.0,
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

Valid `reason` values: see `procu_forge_buyer/doc/a2a_enums.md` → `walkaway_reason`.

---

## Messages you receive

### `QUOTE` from vendor

Vendor's initial response to your RFQ. Round 0 result.

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 50.0,
    "total_price": 5000.0,
    "currency": "USD",
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `COUNTER_OFFER` from vendor

Vendor's counter to your counter. Same shape as the buyer-bound `COUNTER_OFFER`.
The `is_final` boolean signals a best-and-final offer — treat it as the
vendor's last move; respond with `ACCEPT` or `WALKAWAY` only (no further
counters).

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 47.0,
    "total_price": 4700.0,
    "currency": "USD",
    "is_final": false,
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `WALKAWAY` from vendor

Vendor decided your offer is below their floor. Negotiation is over. Mark state `WALKED_AWAY`. No further messages to this vendor.

### `ACCEPT` from vendor

Vendor accepts your latest offer. Lock the deal at the agreed price.

---

## Decision logic (the core loop)

After receiving each `QUOTE` or vendor `COUNTER_OFFER`:

```
if state == WALKED_AWAY:
    stop

if vendor_unit_price <= target_price:
    send ACCEPT
    state = ACCEPTED
    stop

if vendor_is_final or round_count >= 3:
    # cap hit
    send WALKAWAY (reason: MAX_ROUNDS_REACHED)
    state = WALKED_AWAY
    stop

counter = max(target_price, vendor_unit_price * 0.92)
send COUNTER_OFFER at `counter`
round_count += 1
state = NEGOTIATING
```

---

## State diagram

```
RFQ_SENT ──→ QUOTE_RECEIVED
                  │
        ┌─────────┴──────────┐
        ↓                    ↓
   price ≤ target      price > target
        ↓                    ↓
    ACCEPTED         COUNTER_OFFER ──→ vendor COUNTER_OFFER
                          ↑                 │
                          │   ┌─────────────┼─────────────┐
                          │   ↓             ↓             ↓
                          │ is_final=false  is_final=true WALKAWAY (vendor)
                          │   │             │             ↓
                          │   │             │          WALKED_AWAY
                          │   └──────┬──────┘
                          │          ↓
                          │   buyer decides:
                          └── COUNTER_OFFER (if round < 3 and !is_final)
                              ACCEPT          (any round)
                              WALKAWAY        (if round = 3 or is_final
                                               and price > target)
```

---

## Edge cases

- **Response deadline expired** (`response_deadline` in past when you go to respond): emit `WALKAWAY` with `reason: QUOTE_EXPIRED`.
- **Vendor doesn't respond within `response_deadline`**: emit `WALKAWAY` with `reason: VENDOR_REJECTED`.
- **Currency mismatch** in vendor reply: reject the message at validation. Don't try to convert.
- **Vendor's counter price is _higher_ than their previous quote**: protocol violation. Reject at validation.

---

## Handoff

When state becomes `ACCEPTED` or `WALKED_AWAY` for every vendor in the RFQ, the negotiation phase is complete. Persist the outcome for each vendor (price, currency, quantity, state, last round). `buyer_decision` reads this set and picks a winner.

You do **not** call `buyer_decision` directly. You write the outcome to the shared store and your work is done.
