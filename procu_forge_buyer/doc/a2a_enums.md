# Shared: Enum Reference

Source of truth: `schema/communication.json`. This file is a human-readable index.

When you add a new value to any enum here, update the schema first, bump `schema_version`, and notify every agent.

---

## Agent identifiers

| Enum                      | Values                                                                                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `from_agent` / `to_agent` | `buyer_negotiator`, `buyer_decision`, `buyer_po`, `buyer_grn`, `buyer_verification`, `vendor`, `user` _(to_agent only)_, `buyer_system` _(to_agent only)_ |

---

## Negotiation phase

| Enum                        | Values                                                                                             |
| --------------------------- | -------------------------------------------------------------------------------------------------- |
| `COUNTER_RESPONSE.decision` | `COUNTER`, `HOLD`, `REJECT`                                                                        |
| `walkaway_reason`           | `PRICE_GAP_TOO_LARGE`, `MAX_ROUNDS_REACHED`, `VENDOR_REJECTED`, `BUYER_CANCELLED`, `QUOTE_EXPIRED` |

## Vendor selection phase

| Enum                 | Values                                                                                  |
| -------------------- | --------------------------------------------------------------------------------------- |
| `selection_criteria` | `LOWEST_PRICE`, `BEST_VALUE`, `FASTEST_DELIVERY`, `PREFERRED_VENDOR`, `MANUAL_OVERRIDE` |
| `rfq_close_reason`   | `ANOTHER_VENDOR_SELECTED`, `RFQ_CANCELLED`, `NO_SUITABLE_VENDOR`                        |
| `RFQ_CLOSED.outcome` | `NOT_SELECTED`, `CANCELLED`                                                             |

## PO phase

| Enum            | Values                     |
| --------------- | -------------------------- |
| `po_ack_status` | `ACKNOWLEDGED`, `REJECTED` |

## GRN phase

| Enum                        | Values                                                      |
| --------------------------- | ----------------------------------------------------------- |
| `grn_status`                | `COMPLETE`, `PARTIAL`, `DISCREPANCY`                        |
| `GRN line.rejection_reason` | `DAMAGED`, `QUALITY_ISSUE`, `WRONG_ITEM`, `EXPIRED`, `null` |

## Verification phase

| Enum                        | Values                                                                  |
| --------------------------- | ----------------------------------------------------------------------- |
| `verification_status`       | `APPROVED`, `APPROVED_WITH_TOLERANCE`, `REJECTED`                       |
| `verification_check_result` | `PASS`, `FAIL`, `WARNING`                                               |
| `verification_next_action`  | `PROCEED_TO_PAYMENT`, `RESUBMIT_CORRECTED_INVOICE`, `ESCALATE_TO_HUMAN` |
| `discrepancy.severity`      | `BLOCKING`, `WARNING`                                                   |
| `discrepancy.source`        | `PO`, `GRN`                                                             |

## Completion phase

| Enum                      | Values                                                        |
| ------------------------- | ------------------------------------------------------------- |
| `PROCESS_COMPLETE.status` | `READY_FOR_PAYMENT`, `ESCALATED`, `CLOSED_NO_DEAL`            |
| `user_action_required`    | `APPROVE_PAYMENT`, `REVIEW_ESCALATION`, `ACKNOWLEDGE_NO_DEAL` |

## Cross-cutting

| Enum            | Values                                                   |
| --------------- | -------------------------------------------------------- |
| `payment_terms` | `NET_15`, `NET_30`, `NET_45`, `NET_60`, `DUE_ON_RECEIPT` |
| `currency`      | `USD`, `EUR`, `GBP`, `INR`, `JPY`, `CNY`, `AUD`, `CAD`   |
