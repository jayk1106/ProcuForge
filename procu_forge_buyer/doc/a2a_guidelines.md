# Shared: Message Envelope & Protocol

**Read this first.** Every buyer-side agent uses the same message envelope and follows the same protocol rules. This file is the contract. Your phase-specific `SKILL.md` only defines the `payload` shape.

**Schema source of truth:** `schema/communication.json` (v `1.0.0`)
**Companion enum reference:** `_shared/enums.md`

---

## Envelope structure

Every message — RFQ, PO, GRN, invoice, completion — uses this envelope. Only the `payload` shape varies by `message_type`.

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

## Field rules

**`rfq_id`** — threads the entire transaction end-to-end. Every message from RFQ to `PROCESS_COMPLETE` carries the same `rfq_id`. Never mint a new one mid-flow.

**`message_id`** — unique per message. Used for idempotency. Receivers dedupe on this.

**`vendor_id`** — always present, even on internal buyer-side messages. For internal handoffs like `VENDOR_SELECTED`, set it to the selected vendor's id. This keeps the entire transaction filterable by `vendor_id`.

**`round`** — `0` for RFQ, `1-3` for negotiation messages, `null` (or omitted) post-negotiation. The schema doesn't enforce this conditionally; set it correctly yourself.

**`from_agent` / `to_agent`** — restricted to the agent enum plus `user` and `buyer_system` (both valid as `to_agent` only). See `_shared/enums.md`.

**`schema_version`** — every envelope carries it. When bumped (`1.0.0` → `1.1.0`), agents can warn or reject incompatible versions cleanly.

---

## Buyer-side agent map

| Agent                | Phase                          | Owns messages                                     |
| -------------------- | ------------------------------ | ------------------------------------------------- |
| `buyer_negotiator`   | 1. Negotiation                 | RFQ, COUNTER_OFFER, ACCEPT, WALKAWAY (buyer-side) |
| `buyer_decision`     | 2. Vendor Selection            | VENDOR_SELECTED, RFQ_CLOSED                       |
| `buyer_po`           | 3. PO                          | PO                                                |
| `buyer_grn`          | 4. GRN                         | GRN_CREATED                                       |
| `buyer_verification` | 5–6. Verification & Completion | INVOICE_VERIFICATION_RESULT, PROCESS_COMPLETE     |

Vendor side is a single multi-tenant agent identified by `vendor_id`.

---

## Validation (every agent does this)

Validate every inbound message against `schema/communication.json` at the agent boundary, **before any business logic runs**.

1. Validate the envelope against the top-level schema.
2. Dispatch to the matching payload schema under `messages.<TYPE>.payload_schema`.
3. Reject malformed messages with a structured error. Don't try to repair them.

Libraries: `ajv` (Node), `jsonschema` (Python).

---

## Idempotency (every agent does this)

Receivers dedupe on `message_id`. Store seen IDs for at least 24 hours. Without this, network retries cause double-processing — duplicate POs, duplicate GRNs, duplicate invoices.

---

## State per `rfq_id` (every agent does this)

Each agent maintains its own state machine keyed on `rfq_id`. **Don't trust round numbers or status flags from the other side** — verify against your own counters. The other agent's view can drift; yours is authoritative for your phase.

---

## Event log (every agent does this)

Append every message (inbound and outbound) to a per-`rfq_id` log. Even a flat JSON file is fine for a prototype. Critical for debugging async flows when something goes sideways.

Minimum log entry:

```json
{
  "logged_at": "2026-05-09T10:30:01Z",
  "direction": "in" | "out",
  "message_id": "msg_...",
  "rfq_id": "rfq_...",
  "message_type": "...",
  "from_agent": "...",
  "to_agent": "...",
  "payload_hash": "sha256:..."
}
```

---

## Handoff convention

When a phase ends, the owning agent emits the final message of that phase, which doubles as the trigger for the next agent. Examples:

- Negotiator emits `ACCEPT` → decision agent picks it up
- Decision emits `VENDOR_SELECTED` to `buyer_po` → PO agent picks it up
- GRN emits `GRN_CREATED` with `to_agent: buyer_verification` → verification agent picks it up

No agent should peek into another phase's state. If you need data from an earlier phase, read the **persisted artifact** (PO record, GRN record), not the originating agent's in-memory state.

---

## Cycle caps (don't loop forever)

| Loop                      | Cap | On hit                                                          |
| ------------------------- | --- | --------------------------------------------------------------- |
| Negotiation rounds        | 3   | Buyer emits `WALKAWAY` with `reason: MAX_ROUNDS_REACHED`        |
| Invoice correction rounds | 3   | Verification emits result with `next_action: ESCALATE_TO_HUMAN` |

Document tolerance thresholds (e.g., ±2% price) even if hardcoded. Your future self will need them.
