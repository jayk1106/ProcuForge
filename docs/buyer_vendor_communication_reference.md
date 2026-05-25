# Buyer-Vendor Communication Reference

This document is aligned to the agreed buyer-vendor communication flow and schema.

---

## 1) Communication from the Buyer Side

- `SENT REQUEST -> RFQ response -> QUOTE`
- `SENT REQUEST -> COUNTER_OFFER / ACCEPT / WALKAWAY response -> ACCEPT / COUNTER_OFFER / WALKAWAY`
- `SENT REQUEST -> RFQ_CLOSED response -> no need`
- `SENT REQUEST -> PO response -> PO_ACKNOWLEDGED`
- `SENT REQUEST -> GRN_CREATED response -> INVOICE_SUBMITTED`
- `SENT REQUEST -> PROCESS_COMPLETE response -> no need`

---

## 2) Communication from the Vendor Side

- `REQUEST COMES -> RFQ -> Response -> QUOTE`
- `REQUEST COMES -> COUNTER_OFFER / ACCEPT / WALKAWAY -> Response -> ACCEPT / COUNTER_OFFER / WALKAWAY`
- `REQUEST COMES -> RFQ_CLOSED -> RESPONSE ACTION -> close the request`
- `REQUEST COMES -> PO -> RESPONSE -> PO_ACKNOWLEDGED`
- `REQUEST COMES -> GRN_CREATED -> RESPONSE -> INVOICE_SUBMITTED`
- `REQUEST COMES -> PROCESS_COMPLETE -> RESPONSE ACTION -> ends the flow`

---

## 3) Final Schema for Communication

### Common Request/Response Envelope

```json
{
  "message_id": "msg_rfq_001",
  "rfq_id": "rfq_2026_0001",
  "vendor_id": "vendor_123",
  "from_agent": "vendor_agent",
  "to_agent": "buyer_agent",
  "message_type": "RFQ",
  "round": 0,
  "timestamp": "2026-05-09T10:00:00Z",
  "payload": {}
}
```

Notes:

- `from_agent` and `to_agent` must be agent names only (no subagent names).
- Only `payload` changes by `message_type`.

### `RFQ` (from buyer to vendor agent)

```json
{
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

### `QUOTE` (from vendor to buyer agent)

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 1,
    "total_price": 100,
    "currency": "USD",
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `COUNTER_OFFER` (both ways: buyer -> vendor and vendor -> buyer)

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 0.5,
    "total_price": 50,
    "currency": "USD",
    "is_final": false,
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `ACCEPT` (both ways: buyer -> vendor and vendor -> buyer)

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "unit_price": 0.5,
    "total_price": 50,
    "currency": "USD",
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `WALKAWAY` (both ways: buyer -> vendor and vendor -> buyer)

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
    "last_unit_price": 0.4,
    "last_total_price": 40,
    "required_by": "2026-06-15",
    "response_deadline": "2026-05-11T18:00:00Z"
  }
}
```

### `RFQ_CLOSED` (from buyer to vendor)

```json
{
  "payload": {
    "item": {
      "product_id": "prod_widget_a",
      "sku": "ITEM-001",
      "quantity": 100,
      "unit": "pcs"
    },
    "outcome": "NOT_SELECTED",
    "reason": "ANOTHER_VENDOR_SELECTED"
  }
}
```

### `PO` (from buyer to vendor)

```json
{
  "payload": {
    "po_number": "PO-2026-0042",
    "rfq_reference": "rfq_2026_0001",
    "line_items": [
      {
        "sku": "ITEM-001",
        "product_id": "prod_widget_a",
        "quantity": 100,
        "unit_price": 47.0,
        "total_price": 4700.0
      }
    ],
    "total_amount": 4700.0,
    "currency": "USD",
    "delivery_date": "2026-06-15"
  }
}
```

### `PO_ACKNOWLEDGED` (from vendor to buyer)

```json
{
  "payload": {
    "po_number": "PO-2026-0042"
  }
}
```

### `GRN_CREATED` (from buyer to vendor)

```json
{
  "payload": {
    "grn_number": "GRN-2026-0089",
    "po_number": "PO-2026-0042",
    "received_at": "2026-06-14T14:30:00Z",
    "line_items": [
      {
        "sku": "ITEM-001",
        "unit_quantity": 100
      }
    ]
  }
}
```

### `INVOICE_SUBMITTED` (from vendor to buyer)

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
        "total_price": 4700.0
      }
    ],
    "total_amount": 5546.0,
    "currency": "USD",
    "due_date": "2026-07-15"
  }
}
```

### `PROCESS_COMPLETE` (from buyer to vendor)

```json
{
  "payload": {
    "po_number": "PO-2026-0042",
    "grn_number": "GRN-2026-0089",
    "invoice_number": "INV-V123-2026-0017-R1"
  }
}
```
