"""Drive the WebSocket layer with mock state_changed broadcasts.

Walks a workflow detail page and a vendor thread page through a realistic
sequence of state transitions so you can watch the UI update in real time
without having to drive a full buyer-agent run.

Usage
-----
    # 1. Start the API (with the websockets-sansio impl):
    #    uv run uvicorn api.main:app --reload --port 8000 --ws websockets-sansio
    #
    # 2. Open both pages in your browser (NEXT_PUBLIC_WS_DEBUG=1 in web/.env.local):
    #    http://localhost:3000/flows/cd5b166d-318c-4d24-b32a-f1a547a98939
    #    http://localhost:3000/vendors/02e9367c-fa32-40c9-8200-859b34a77384
    #
    # 3. Run this script (no install needed; uses stdlib only):
    #    uv run python scripts/test_ws_events.py
    #
    # 4. Watch both pages tick through the stages. Server logs show
    #    `ws.broadcast.sent channel=<id> seq=N reason=stage_…`.
    #    Browser console (with WS debug on) shows `[ws][flow|vendor] state-applied seq=N`.

Optional flags
--------------
    --api http://localhost:8000   # API base URL
    --workflow <uuid>             # override the workflow id
    --rfq <uuid>                  # override the rfq id
    --delay 1.0                   # seconds between stages (default 1.0)
    --only flow|vendor|both       # which page to drive (default both)

The endpoint hit is ``POST /api/v1/test/ws-broadcast``. The payload shapes
follow the ``ActiveFlow`` / ``VendorConvo`` TypeScript types in
``web/src/types/index.ts`` so the UI renders the mock data as if it came
from the real DTO factories.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API = "http://localhost:8000"
DEFAULT_WORKFLOW_ID = "cd5b166d-318c-4d24-b32a-f1a547a98939"
DEFAULT_RFQ_ID = "02e9367c-fa32-40c9-8200-859b34a77384"
DEFAULT_DELAY_SECONDS = 1.0


# ── HTTP helper ───────────────────────────────────────────────────────────────


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {exc.reason} from {url}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach {url}: {exc.reason}") from exc


def broadcast(
    api: str,
    *,
    channel: str,
    reason: str,
    payload: dict[str, Any],
    workflow_id: str | None = None,
    vendor_thread_id: str | None = None,
) -> None:
    body = {
        "channel": channel,
        "reason": reason,
        "payload": payload,
        "workflow_id": workflow_id,
        "vendor_thread_id": vendor_thread_id,
    }
    result = post_json(f"{api}/api/v1/test/ws-broadcast", body)
    print(
        f"  ▸ scheduled channel={result.get('channel')} reason={result.get('reason')}"
    )


# ── Workflow (ActiveFlow) mock builder ────────────────────────────────────────


def base_flow(workflow_id: str) -> dict[str, Any]:
    """Common fields shared across every workflow stage."""
    return {
        "id": workflow_id,
        "requestId": f"PR-{workflow_id[:8].upper()}",
        "title": "Optical mouse · 200 units",
        "requester": "kaneriyajay3@gmail.com",
        "costCenter": "CC-ENG-01",
        "opened": "2026-06-05",
        "target": 4800.00,
        "needBy": "2026-06-30",
        "spec": "USB-A wired, ergonomic, 1600 DPI, 18-month warranty.",
        "phaseDurations": {
            "rfq": None,
            "neg": None,
            "po": None,
            "grn": None,
            "inv": None,
            "done": None,
        },
        "specDone": True,
        "discoveredVendors": [],
        "vendors": [],
        "activity": [],
        "po": None,
        "grn": None,
        "invoice": None,
        "selectedVendor": None,
    }


def workflow_stages(workflow_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Yield (reason, ActiveFlow-shaped payload) tuples in narrative order."""
    stages: list[tuple[str, dict[str, Any]]] = []

    # 1. Just kicked off — vendor search in progress.
    s = base_flow(workflow_id)
    s.update(
        prStatus="INITIATED",
        currentPhase="rfq",
        phaseStatus={
            "rfq": "in_progress", "neg": "pending", "po": "pending",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        activity=[{"at": "10:00:00", "label": "Workflow created"}],
    )
    stages.append(("stage_1_initiated", s))

    # 2. Discovered 2 vendors.
    s = base_flow(workflow_id)
    s.update(
        prStatus="VENDORS_DISCOVERED",
        currentPhase="rfq",
        phaseStatus={
            "rfq": "done", "neg": "pending", "po": "pending",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        discoveredVendors=[
            {
                "id": "v-acme",
                "name": "Acme Peripherals",
                "country": "US",
                "sku": "MX-100",
                "unit": "ea",
                "unitPrice": 26.00,
                "currency": "USD",
                "leadTimeDays": 7,
                "contracted": True,
                "availabilityStatus": "in_stock",
            },
            {
                "id": "v-zenith",
                "name": "Zenith Trading",
                "country": "DE",
                "sku": "ZN-2200",
                "unit": "ea",
                "unitPrice": 28.50,
                "currency": "USD",
                "leadTimeDays": 12,
                "contracted": False,
                "availabilityStatus": "in_stock",
            },
        ],
        activity=[
            {"at": "10:00:00", "label": "Workflow created"},
            {"at": "10:00:14", "label": "Vendors discovered: 2"},
        ],
    )
    stages.append(("stage_2_vendors_discovered", s))

    # 3. Negotiation in progress, first quotes in.
    s = base_flow(workflow_id)
    s.update(
        prStatus="NEGOTIATION_IN_PROGRESS",
        currentPhase="neg",
        phaseStatus={
            "rfq": "done", "neg": "in_progress", "po": "pending",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        vendors=[
            {
                "id": "v-acme", "vendorId": "v-acme", "workflowId": workflow_id,
                "name": "Acme Peripherals", "country": "US",
                "status": "NEGOTIATING", "round": 1,
                "first": 26.00, "latest": 26.00, "latestPrice": 26.00,
                "lead": "7d", "moq": "1", "messages": [],
            },
            {
                "id": "v-zenith", "vendorId": "v-zenith", "workflowId": workflow_id,
                "name": "Zenith Trading", "country": "DE",
                "status": "NEGOTIATING", "round": 1,
                "first": 28.50, "latest": 28.50, "latestPrice": 28.50,
                "lead": "12d", "moq": "1", "messages": [],
            },
        ],
        activity=[
            {"at": "10:00:14", "label": "Vendors discovered: 2"},
            {"at": "10:00:30", "label": "Negotiation opened"},
        ],
    )
    stages.append(("stage_3_negotiation_open", s))

    # 4. Counter-offers landed, prices down.
    s = base_flow(workflow_id)
    s.update(
        prStatus="NEGOTIATION_IN_PROGRESS",
        currentPhase="neg",
        phaseStatus={
            "rfq": "done", "neg": "in_progress", "po": "pending",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        vendors=[
            {
                "id": "v-acme", "vendorId": "v-acme", "workflowId": workflow_id,
                "name": "Acme Peripherals", "country": "US",
                "status": "NEGOTIATING", "round": 2,
                "first": 26.00, "latest": 23.50, "latestPrice": 23.50,
                "lead": "7d", "moq": "1", "messages": [],
            },
            {
                "id": "v-zenith", "vendorId": "v-zenith", "workflowId": workflow_id,
                "name": "Zenith Trading", "country": "DE",
                "status": "NEGOTIATING", "round": 2,
                "first": 28.50, "latest": 25.75, "latestPrice": 25.75,
                "lead": "12d", "moq": "1", "messages": [],
            },
        ],
        activity=[
            {"at": "10:00:30", "label": "Negotiation opened"},
            {"at": "10:00:52", "label": "Round 2 counter-offers received"},
        ],
    )
    stages.append(("stage_4_counter_offers", s))

    # 5. Awarded to Acme.
    s = base_flow(workflow_id)
    s.update(
        prStatus="AWAITING_USER_APPROVAL",
        currentPhase="neg",
        phaseStatus={
            "rfq": "done", "neg": "done", "po": "pending",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        needsAction=True,
        actionLabel="Approve PO issuance",
        vendors=[
            {
                "id": "v-acme", "vendorId": "v-acme", "workflowId": workflow_id,
                "name": "Acme Peripherals", "country": "US",
                "status": "WON", "round": 2,
                "first": 26.00, "latest": 23.50, "latestPrice": 23.50,
                "lead": "7d", "moq": "1", "messages": [],
            },
            {
                "id": "v-zenith", "vendorId": "v-zenith", "workflowId": workflow_id,
                "name": "Zenith Trading", "country": "DE",
                "status": "LOST", "round": 2,
                "first": 28.50, "latest": 25.75, "latestPrice": 25.75,
                "lead": "12d", "moq": "1", "messages": [],
            },
        ],
        selectedVendor={
            "vendor": "Acme Peripherals", "vendor_id": "v-acme",
            "final_price": 23.50, "outcome": "ACCEPTED",
        },
        activity=[
            {"at": "10:00:52", "label": "Round 2 counter-offers received"},
            {"at": "10:01:10", "label": "Awarded to Acme Peripherals @ 23.50"},
        ],
    )
    stages.append(("stage_5_awarded", s))

    # 6. PO issued + acknowledged.
    s = base_flow(workflow_id)
    s.update(
        prStatus="PO_ACKNOWLEDGED",
        currentPhase="po",
        phaseStatus={
            "rfq": "done", "neg": "done", "po": "in_progress",
            "grn": "pending", "inv": "pending", "done": "pending",
        },
        vendors=[
            {
                "id": "v-acme", "vendorId": "v-acme", "workflowId": workflow_id,
                "name": "Acme Peripherals", "country": "US",
                "status": "WON", "round": 2,
                "first": 26.00, "latest": 23.50, "latestPrice": 23.50,
                "lead": "7d", "moq": "1", "messages": [],
            },
        ],
        selectedVendor={
            "vendor": "Acme Peripherals", "vendor_id": "v-acme",
            "final_price": 23.50, "outcome": "ACCEPTED",
        },
        po={
            "po_number": "PO-A1B2C3D4",
            "total_amount": 4700.00,
            "currency": "USD",
            "delivery_date": "2026-06-26",
            "agreed_price": 23.50,
        },
        activity=[
            {"at": "10:01:10", "label": "Awarded to Acme Peripherals @ 23.50"},
            {"at": "10:01:25", "label": "PO PO-A1B2C3D4 acknowledged"},
        ],
    )
    stages.append(("stage_6_po_acknowledged", s))

    # 7. GRN + invoice received, status completed.
    s = base_flow(workflow_id)
    s.update(
        prStatus="COMPLETED",
        currentPhase="done",
        phaseStatus={
            "rfq": "done", "neg": "done", "po": "done",
            "grn": "done", "inv": "done", "done": "done",
        },
        vendors=[
            {
                "id": "v-acme", "vendorId": "v-acme", "workflowId": workflow_id,
                "name": "Acme Peripherals", "country": "US",
                "status": "WON", "round": 2,
                "first": 26.00, "latest": 23.50, "latestPrice": 23.50,
                "lead": "7d", "moq": "1", "messages": [],
            },
        ],
        selectedVendor={
            "vendor": "Acme Peripherals", "vendor_id": "v-acme",
            "final_price": 23.50, "outcome": "ACCEPTED",
        },
        po={
            "po_number": "PO-A1B2C3D4", "total_amount": 4700.00,
            "currency": "USD", "delivery_date": "2026-06-26",
            "agreed_price": 23.50,
        },
        grn={"grn_number": "GRN-9F8E7D", "po_number": "PO-A1B2C3D4",
             "received_at": "2026-06-22T12:00:00Z"},
        invoice={"invoice_number": "INV-44221", "po_number": "PO-A1B2C3D4",
                 "total_amount": 4700.00, "currency": "USD"},
        activity=[
            {"at": "10:01:25", "label": "PO PO-A1B2C3D4 acknowledged"},
            {"at": "10:01:45", "label": "GRN GRN-9F8E7D recorded"},
            {"at": "10:02:00", "label": "Invoice INV-44221 matched"},
            {"at": "10:02:05", "label": "Workflow complete"},
        ],
    )
    stages.append(("stage_7_completed", s))

    return stages


# ── Vendor thread (VendorConvo) mock builder ──────────────────────────────────


def base_convo(rfq_id: str, workflow_id: str) -> dict[str, Any]:
    return {
        "vendor": {
            "id": "v-acme",
            "name": "Acme Peripherals",
            "country": "US",
            "tier": "Tier-2",
            "mssa": "active",
        },
        "product": {
            "id": "p-mouse-200",
            "name": "Optical mouse (200 ea)",
            "sku": "MX-100",
            "brand": "Acme",
            "type": "peripheral",
        },
        "pr": workflow_id,
        "workflowId": workflow_id,
        "rfqId": rfq_id,
        "outcome": "INITIATED",
        "summary": {
            "status": "INITIATED",
            "quotedPrice": None,
            "acceptedPrice": None,
            "latestOfferPrice": None,
            "lastSellingPrice": None,
            "currency": "USD",
            "poNumber": None,
            "grnNumber": None,
            "invoiceNumber": None,
            "expectedDelivery": None,
            "deliveredOn": None,
        },
        "messages": [],
    }


def _msg(
    ts: str, mtype: str, from_a: str, to_a: str, payload: dict[str, Any],
    *, round_n: int | None = None, highlight: str = "",
) -> dict[str, Any]:
    phase_map = {
        "RFQ": "negotiation", "QUOTE": "negotiation",
        "COUNTER_OFFER": "negotiation", "ACCEPT": "negotiation",
        "PO": "fulfillment", "PO_ACKNOWLEDGED": "fulfillment",
        "GRN_CREATED": "fulfillment", "INVOICE_SUBMITTED": "fulfillment",
        "PROCESS_COMPLETE": "fulfillment",
    }
    return {
        "ts": ts, "from": from_a, "to": to_a, "type": mtype,
        "phase": phase_map.get(mtype, "other"),
        "payload": payload, "highlight": highlight, "round": round_n,
    }


def convo_stages(rfq_id: str, workflow_id: str) -> list[tuple[str, dict[str, Any]]]:
    stages: list[tuple[str, dict[str, Any]]] = []

    # 1. Thread initiated, no messages.
    stages.append(("stage_1_initiated", base_convo(rfq_id, workflow_id)))

    # 2. RFQ sent (outbound).
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = [
        _msg(
            "2026-06-05 10:00:30", "RFQ", "buyer", "v-acme",
            {
                "item": {"product_id": "p-mouse-200", "sku": "MX-100",
                         "quantity": 200, "unit": "ea"},
                "required_by": "2026-06-30",
                "response_deadline": "2026-06-08",
            },
            round_n=0,
        ),
    ]
    s["outcome"] = "RFQ_SENT"
    s["summary"]["status"] = "AWAITING_QUOTE"
    stages.append(("stage_2_rfq_sent", s))

    # 3. QUOTE inbound.
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = [
        _msg(
            "2026-06-05 10:00:30", "RFQ", "buyer", "v-acme",
            {"item": {"product_id": "p-mouse-200", "sku": "MX-100",
                      "quantity": 200, "unit": "ea"},
             "required_by": "2026-06-30",
             "response_deadline": "2026-06-08"},
            round_n=0,
        ),
        _msg(
            "2026-06-05 10:00:42", "QUOTE", "v-acme", "buyer",
            {"item": {"product_id": "p-mouse-200", "sku": "MX-100",
                      "quantity": 200, "unit": "ea"},
             "unit_price": 26.00, "total_price": 5200.00,
             "required_by": "2026-06-30",
             "response_deadline": "2026-06-09"},
            round_n=1, highlight="$26.00 / $5,200.00",
        ),
    ]
    s["outcome"] = "QUOTED"
    s["summary"].update(status="QUOTED", quotedPrice=26.00, latestOfferPrice=26.00)
    stages.append(("stage_3_quote_received", s))

    # 4. COUNTER_OFFER outbound.
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = stages[-1][1]["messages"] + [
        _msg(
            "2026-06-05 10:00:50", "COUNTER_OFFER", "buyer", "v-acme",
            {"item": {"product_id": "p-mouse-200", "sku": "MX-100",
                      "quantity": 200, "unit": "ea"},
             "unit_price": 23.00, "total_price": 4600.00,
             "is_final": False,
             "required_by": "2026-06-30",
             "response_deadline": "2026-06-09"},
            round_n=2, highlight="$23.00 / $4,600.00",
        ),
    ]
    s["outcome"] = "NEGOTIATING"
    s["summary"].update(status="NEGOTIATING", latestOfferPrice=23.00)
    stages.append(("stage_4_counter_outbound", s))

    # 5. ACCEPT inbound at midpoint.
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = stages[-1][1]["messages"] + [
        _msg(
            "2026-06-05 10:01:05", "ACCEPT", "v-acme", "buyer",
            {"item": {"product_id": "p-mouse-200", "sku": "MX-100",
                      "quantity": 200, "unit": "ea"},
             "unit_price": 23.50, "total_price": 4700.00},
            round_n=3, highlight="$23.50 / $4,700.00",
        ),
    ]
    s["outcome"] = "ACCEPTED @ 23.5"
    s["summary"].update(status="ACCEPTED", acceptedPrice=23.50, lastSellingPrice=23.50)
    stages.append(("stage_5_accepted", s))

    # 6. PO sent + acknowledged.
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = stages[-1][1]["messages"] + [
        _msg(
            "2026-06-05 10:01:25", "PO", "buyer", "v-acme",
            {"po_number": "PO-A1B2C3D4", "rfq_reference": rfq_id,
             "total_amount": 4700.00, "currency": "USD",
             "delivery_date": "2026-06-26"},
            highlight="PO-A1B2C3D4",
        ),
        _msg(
            "2026-06-05 10:01:30", "PO_ACKNOWLEDGED", "v-acme", "buyer",
            {"po_number": "PO-A1B2C3D4"},
            highlight="ack PO-A1B2C3D4",
        ),
    ]
    s["outcome"] = "PO_ACKNOWLEDGED"
    s["summary"].update(status="PO_ACKNOWLEDGED", poNumber="PO-A1B2C3D4",
                        expectedDelivery="2026-06-26")
    stages.append(("stage_6_po_acknowledged", s))

    # 7. GRN + invoice + process complete.
    s = base_convo(rfq_id, workflow_id)
    s["messages"] = stages[-1][1]["messages"] + [
        _msg(
            "2026-06-05 10:01:45", "GRN_CREATED", "buyer", "v-acme",
            {"grn_number": "GRN-9F8E7D", "po_number": "PO-A1B2C3D4",
             "received_at": "2026-06-22T12:00:00Z"},
            highlight="GRN-9F8E7D",
        ),
        _msg(
            "2026-06-05 10:01:55", "INVOICE_SUBMITTED", "v-acme", "buyer",
            {"invoice_number": "INV-44221", "po_number": "PO-A1B2C3D4",
             "grn_reference": "GRN-9F8E7D", "invoice_date": "2026-06-23",
             "due_date": "2026-07-23", "total_amount": 4700.00,
             "currency": "USD"},
            highlight="INV-44221",
        ),
        _msg(
            "2026-06-05 10:02:05", "PROCESS_COMPLETE", "buyer", "v-acme",
            {"po_number": "PO-A1B2C3D4", "grn_number": "GRN-9F8E7D",
             "invoice_number": "INV-44221"},
            highlight="complete",
        ),
    ]
    s["outcome"] = "COMPLETE"
    s["summary"].update(
        status="COMPLETE", grnNumber="GRN-9F8E7D",
        invoiceNumber="INV-44221", deliveredOn="2026-06-22",
    )
    stages.append(("stage_7_complete", s))

    return stages


# ── Driver ────────────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> None:
    api = args.api.rstrip("/")
    workflow_id = args.workflow
    rfq_id = args.rfq

    print(f"API           : {api}")
    print(f"workflow_id   : {workflow_id}")
    print(f"rfq_id        : {rfq_id}")
    print(f"delay between : {args.delay}s")
    print()

    flow_seq = workflow_stages(workflow_id) if args.only in ("flow", "both") else []
    convo_seq = convo_stages(rfq_id, workflow_id) if args.only in ("vendor", "both") else []

    # Interleave so both pages tick together when --only both.
    total = max(len(flow_seq), len(convo_seq))
    for i in range(total):
        if i < len(flow_seq):
            reason, payload = flow_seq[i]
            print(f"[flow  ] {reason}")
            broadcast(
                api,
                channel=workflow_id,
                reason=f"flow_{reason}",
                payload=payload,
                workflow_id=workflow_id,
            )
        if i < len(convo_seq):
            reason, payload = convo_seq[i]
            print(f"[vendor] {reason}")
            broadcast(
                api,
                channel=f"vt:{rfq_id}",
                reason=f"vendor_{reason}",
                payload=payload,
                workflow_id=workflow_id,
                vendor_thread_id=rfq_id,
            )
        if i < total - 1:
            time.sleep(args.delay)

    print()
    print("Done. Server logs should show one `ws.broadcast.sent` per stage")
    print("(skips with reason=same_hash mean the previous payload was identical).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW_ID)
    parser.add_argument("--rfq", default=DEFAULT_RFQ_ID)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--only", choices=("flow", "vendor", "both"), default="both")
    args = parser.parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
