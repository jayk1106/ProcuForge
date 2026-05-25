# Shared: Enum Reference

Source of truth: `schema/communication.json`. This file is a human-readable index.

When you add a new value to any enum here, update the schema first and notify every agent.

---

## Agent identifiers

| Enum                      | Values                          |
| ------------------------- | ------------------------------- |
| `from_agent` / `to_agent` | `buyer_agent`, `vendor_agent`   |

Internal subagent routing (decision, PO, GRN, verification) is _not_ exposed
on the wire — envelopes only carry the two canonical agent identifiers above.

---

## Negotiation phase

| Enum              | Values                                                                                             |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| `walkaway_reason` | `PRICE_GAP_TOO_LARGE`, `MAX_ROUNDS_REACHED`, `VENDOR_REJECTED`, `BUYER_CANCELLED`, `QUOTE_EXPIRED` |

`COUNTER_OFFER` is bidirectional. The `is_final` boolean on a vendor
`COUNTER_OFFER` marks a best-and-final offer (replaces the previous
`COUNTER_RESPONSE.decision` enum which has been removed).

## Vendor selection phase

| Enum                 | Values                                                                                  |
| -------------------- | --------------------------------------------------------------------------------------- |
| `selection_criteria` | `LOWEST_PRICE`, `BEST_VALUE`, `FASTEST_DELIVERY`, `PREFERRED_VENDOR`, `MANUAL_OVERRIDE` |
| `RFQ_CLOSED.outcome` | `NOT_SELECTED`, `CANCELLED`                                                             |
| `RFQ_CLOSED.reason`  | `ANOTHER_VENDOR_SELECTED`, `RFQ_CANCELLED`, `NO_SUITABLE_VENDOR`                        |

## Cross-cutting

| Enum       | Values                                                   |
| ---------- | -------------------------------------------------------- |
| `currency` | `USD`, `EUR`, `GBP`, `INR`, `JPY`, `CNY`, `AUD`, `CAD`   |
