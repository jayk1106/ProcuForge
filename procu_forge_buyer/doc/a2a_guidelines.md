# Shared: Message Envelope & Protocol

**Read this first.** Every buyer-side agent uses the same message envelope and follows the same protocol rules. This file is the contract. Your phase-specific `SKILL.md` only defines the `payload` shape.

**Schema source of truth:** `schema/communication.json`
**Companion enum reference:** `procu_forge_buyer/doc/a2a_enums.md`
**Reference doc:** `docs/buyer_vendor_communication_reference.md`

---

## Envelope structure

Every message — RFQ, PO, GRN, invoice, completion — uses this envelope. Only the `payload` shape varies by `message_type`.

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
  "payload": { }
}
```

## Field rules

**`rfq_id`** — threads the entire transaction end-to-end. Every message from RFQ to `PROCESS_COMPLETE` carries the same `rfq_id`. Never mint a new one mid-flow.

**`message_id`** — unique per message. Used for idempotency. Receivers dedupe on this.

**`vendor_id`** — always present, even on internal buyer-side messages. Keeps the entire transaction filterable by `vendor_id`.

**`round`** — `0` for RFQ, `1-3` for negotiation messages, `null` post-negotiation. Set it correctly yourself.

**`from_agent` / `to_agent`** — restricted to `buyer_agent` and `vendor_agent`. Subagent identity is not exposed on the wire.

---

## Buyer-side agent map (internal only)

| Subagent             | Phase                          | Owns messages                                     |
| -------------------- | ------------------------------ | ------------------------------------------------- |
| `buyer_negotiator`   | 1. Negotiation                 | RFQ, COUNTER_OFFER, ACCEPT, WALKAWAY (buyer-side) |
| `buyer_decision`     | 2. Vendor Selection            | RFQ_CLOSED                                        |
| `buyer_po`           | 3. PO                          | PO                                                |
| `buyer_grn`          | 4. GRN                         | GRN_CREATED                                       |
| `buyer_verification` | 5–6. Verification & Completion | PROCESS_COMPLETE                                  |

These names are routing details inside the buyer agent only. Envelopes
crossing the wire use `from_agent: "buyer_agent"` regardless of which
subagent produced them. The vendor side mirrors this with `vendor_agent`.

---

## Validation (every agent does this)

Validate every inbound message against `schema/communication.json` at the agent boundary, **before any business logic runs**.

1. Validate the envelope against the top-level schema.
2. Dispatch to the matching payload schema under `messages.<TYPE>.payload_schema`.
3. Reject malformed messages with a structured error. Don't try to repair them.

Libraries: `ajv` (Node), `jsonschema` (Python).

---

## Idempotency (every agent does this)

Receivers dedupe on `message_id`. Store seen IDs for at least 24 hours. Without this, network retries cause double-processing.

---

## State per `rfq_id` (every agent does this)

Each agent maintains its own state machine keyed on `rfq_id`. **Don't trust round numbers or status flags from the other side** — verify against your own counters.

---

## Event log (every agent does this)

Append every message (inbound and outbound) to a per-`rfq_id` log. Even a flat JSON file is fine for a prototype. Critical for debugging async flows.

Minimum log entry:

```json
{
  "logged_at": "2026-05-09T10:30:01Z",
  "direction": "in",
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

When a phase ends, the owning subagent emits the final message of that phase, which doubles as the trigger for the next subagent. Examples:

- Negotiator emits `ACCEPT` → decision subagent picks it up internally.
- Decision emits `RFQ_CLOSED` (vendor-bound) for non-selected vendors.
- GRN emits `GRN_CREATED` → verification subagent picks it up.

No subagent should peek into another phase's state. Read the **persisted artifact** (PO record, GRN record), not the originating agent's in-memory state.

---

## Cycle caps (don't loop forever)

| Loop                 | Cap | On hit                                                          |
| -------------------- | --- | --------------------------------------------------------------- |
| Negotiation rounds   | 3   | Buyer emits `WALKAWAY` with `reason: MAX_ROUNDS_REACHED`        |

Document tolerance thresholds (e.g., ±2% price) even if hardcoded.
