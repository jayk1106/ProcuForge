"""Map ADK session.state dicts to UI-facing DTOs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.schemas.ui_dto import (
    ActiveVendorDTO,
    ActivityItemDTO,
    DiscoveredVendorDTO,
    VendorConvoDTO,
    VendorThreadMessageDTO,
    VendorThreadRowDTO,
    VendorThreadSummaryDTO,
    WorkflowDetailDTO,
    WorkflowRowDTO,
)
from api.schemas.vendor_thread_status import (
    infer_vendor_thread_status,
    to_active_vendor_status,
    to_state_label,
)
from api.services.status_mapping import (
    action_label,
    effective_pr_status,
    is_walked_away,
    needs_action,
    parse_pr_status,
    phase_status_map,
    pr_status_human_label,
    pr_status_to_phase_id,
    pr_status_to_phase_label,
    spec_done,
)
from db.collections.product import Product
from db.collections.vendor import Vendor
from db.collections.workflow_event import WorkflowEventDoc
from procu_forge_buyer.state_keys import (
    GRN_KEY,
    INVOICE_KEY,
    NEGOTIATION_CONFIG_KEY,
    PO_KEY,
    PR_STATUS_KEY,
    REQUEST_KEY,
    SELECTED_VENDOR_KEY,
    VENDOR_OFFERS_KEY,
    VENDOR_THREAD_OVERRIDES_KEY,
)


def _thread_overrides(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get(VENDOR_THREAD_OVERRIDES_KEY)
    return raw if isinstance(raw, dict) else {}


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _days_since(raw: str | None) -> int:
    dt = _parse_dt(raw)
    if dt is None:
        return 0
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _format_relative(raw: str | None) -> str:
    days = _days_since(raw)
    if days == 0:
        return "today"
    if days == 1:
        return "1d ago"
    return f"{days}d ago"


def _vendor_country(vendor_doc: Vendor | None) -> str:
    if vendor_doc is None:
        return "—"
    address = getattr(vendor_doc, "address", None)
    country = getattr(address, "country", None) if address is not None else None
    return country or "—"


def _vendor_count(state: dict[str, Any]) -> int:
    neg = state.get(NEGOTIATION_CONFIG_KEY)
    if isinstance(neg, dict) and neg:
        return len(neg)
    offers = state.get(VENDOR_OFFERS_KEY)
    if isinstance(offers, dict):
        count = _get(offers, "offerCount", "offer_count")
        if isinstance(count, int):
            return count
        offer_list = offers.get("offers")
        if isinstance(offer_list, list):
            return len(offer_list)
    return 0


def _latest_price_from_communications(comms: list[Any]) -> float | None:
    for entry in reversed(comms):
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        if isinstance(payload, dict):
            for key in ("unit_price", "unitPrice", "price"):
                val = payload.get(key)
                if isinstance(val, (int, float)):
                    return float(val)
    return None


def _build_thread_preview(comms: list[Any], limit: int = 3) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for entry in comms[-limit:]:
        if not isinstance(entry, dict):
            continue
        msg_type = str(entry.get("message_type") or entry.get("messageType") or "MSG")
        round_num = entry.get("round")
        preview.append(
            {
                "who": "them" if entry.get("from_agent") == "vendor_agent" else "us",
                "what": msg_type,
                "meta": f"round {round_num}" if round_num is not None else "",
            }
        )
    return preview


def _event_to_activity(event: WorkflowEventDoc) -> ActivityItemDTO:
    ts = event.ts.strftime("%Y-%m-%d %H:%M") if event.ts else ""
    payload = event.payload if isinstance(event.payload, dict) else {}
    detail = _activity_detail_for_event(event.event_type, payload)
    return ActivityItemDTO(ts=ts, ag=event.author or "system", det=detail)


def _activity_detail_for_event(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "vendor_thread_initiated":
        return f"Started thread with vendor {payload.get('vendor_id', '?')}"
    if event_type == "vendor_message_outbound":
        return f"→ {payload.get('message_type') or 'MSG'} (round {payload.get('round')}) to vendor {payload.get('vendor_id', '?')}"
    if event_type == "vendor_message_inbound":
        return f"← {payload.get('message_type') or 'reply'} from vendor {payload.get('vendor_id', '?')}"
    if event_type == "pr_status_changed":
        return f"Status {payload.get('previous') or '?'} → {payload.get('current') or '?'}"
    if event_type == "vendor_thread_escalated":
        return f"Escalated thread {payload.get('rfq_id', '?')}"
    if event_type == "vendor_thread_walked_away":
        return f"Walked away from thread {payload.get('rfq_id', '?')}"
    return event_type.replace("_", " ")


def workflow_row_from_state(
    workflow_id: str,
    state: dict[str, Any],
    *,
    product_name: str | None = None,
) -> WorkflowRowDTO:
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    product = state.get("product") if isinstance(state.get("product"), dict) else {}
    pr_status = effective_pr_status(state)

    qty = _get(request, "quantity", default="")
    pid = _get(request, "product_id", "productId", default="")
    pname = product_name or _get(product, "name", default=pid) or workflow_id
    product_label = f"{pname} × {qty}" if qty else str(pname)

    created_at = _get(request, "created_at", "createdAt", default="")
    request_id = _get(request, "request_id", "requestId", default=workflow_id)

    return WorkflowRowDTO(
        id=workflow_id,
        requestId=str(request_id),
        product=product_label,
        requestedBy=str(_get(request, "requester_id", "requesterId", default="unknown")),
        requestedAt=str(created_at)[:10] if created_at else "",
        phase=pr_status_to_phase_label(pr_status),  # type: ignore[arg-type]
        currentState=pr_status_human_label(pr_status),
        vendors=_vendor_count(state),
        days=_days_since(str(created_at) if created_at else None),
        needsAction=needs_action(pr_status),
        actionLabel=action_label(pr_status),
        walked=is_walked_away(pr_status),
    )


def workflow_detail_from_state(
    workflow_id: str,
    state: dict[str, Any],
    *,
    vendor_names: dict[str, Vendor] | None = None,
    events: list[WorkflowEventDoc] | None = None,
) -> WorkflowDetailDTO:
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    product = state.get("product") if isinstance(state.get("product"), dict) else {}
    pr_status = effective_pr_status(state)
    vendor_names = vendor_names or {}

    budget = _get(request, "budget_ceiling", "budgetCeiling", default=0)
    target = float(budget) if budget else 0.0

    selected = state.get(SELECTED_VENDOR_KEY)
    selected_vendor_id: str | None = None
    if isinstance(selected, dict):
        selected_vendor_id = str(_get(selected, "vendor", default="") or "") or None

    offers_blob = state.get(VENDOR_OFFERS_KEY)
    offer_by_vendor: dict[str, dict[str, Any]] = {}
    if isinstance(offers_blob, dict):
        offer_list = offers_blob.get("offers")
        if isinstance(offer_list, list):
            for offer in offer_list:
                if not isinstance(offer, dict):
                    continue
                vid = str(_get(offer, "vendorId", "vendor_id", default=""))
                if vid:
                    offer_by_vendor[vid] = offer

    overrides = _thread_overrides(state)
    neg_config = state.get(NEGOTIATION_CONFIG_KEY)
    vendors: list[ActiveVendorDTO] = []
    if isinstance(neg_config, dict):
        for vid, cfg in neg_config.items():
            if not isinstance(cfg, dict):
                continue
            vendor_id = str(cfg.get("vendor_id") or vid)
            vendor_doc = vendor_names.get(vendor_id)
            name = vendor_doc.name if vendor_doc else vendor_id
            country = _vendor_country(vendor_doc)
            comms = cfg.get("communications")
            comms_list = comms if isinstance(comms, list) else []
            latest = _latest_price_from_communications(comms_list)
            delta = (latest - target) if latest is not None and target else None
            round_val = cfg.get("round")
            rfq_id = str(cfg.get("rfq_id") or "")
            thread_status = infer_vendor_thread_status(
                cfg,
                selected_vendor_id=selected_vendor_id,
                override=overrides.get(rfq_id) if rfq_id else None,
            )
            prod = cfg.get("product") if isinstance(cfg.get("product"), dict) else {}
            offer = offer_by_vendor.get(vendor_id, {})
            lead_days = _get(prod, "lead_time_days", "leadTimeDays") or _get(
                offer, "leadTimeDays", "lead_time_days"
            )
            moq = _get(prod, "minimum_order_qty", "minimumOrderQty", default=1)

            vendors.append(
                ActiveVendorDTO(
                    id=vendor_id,
                    rfqId=rfq_id,
                    name=name,
                    country=country,
                    round=f"R{round_val}" if round_val is not None else "R0",
                    state=to_state_label(thread_status),
                    status=to_active_vendor_status(thread_status),
                    latest=latest,
                    delta=delta,
                    moq=int(moq) if isinstance(moq, (int, float)) else 1,
                    lead=f"{lead_days}d" if lead_days is not None else "—",
                    escalated=thread_status.name == "ESCALATED",
                    thread=_build_thread_preview(comms_list),
                )
            )

    if events:
        activity = [_event_to_activity(e) for e in events]
    else:
        activity = []
        created_at = _get(request, "created_at", "createdAt")
        if created_at:
            activity.append(
                ActivityItemDTO(
                    ts=str(created_at)[:16].replace("T", " "),
                    ag="system",
                    det="Workflow initiated",
                )
            )
        prev = state.get("previous_pr_status")
        curr = state.get(PR_STATUS_KEY)
        if prev and curr and prev != curr:
            activity.append(
                ActivityItemDTO(
                    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    ag="buyer_agent",
                    det=f"Status {prev} → {curr}",
                )
            )

    created_at = _get(request, "created_at", "createdAt")
    request_id = _get(request, "request_id", "requestId", default=workflow_id)
    title = _get(product, "name", default=request_id)

    discovered: list[DiscoveredVendorDTO] = []
    for vid, offer in offer_by_vendor.items():
        vendor_doc = vendor_names.get(vid)
        unit_price = _coerce_float(_get(offer, "unitPrice", "unit_price"))
        lead_raw = _get(offer, "leadTimeDays", "lead_time_days")
        lead_days = int(lead_raw) if isinstance(lead_raw, (int, float)) else None
        discovered.append(
            DiscoveredVendorDTO(
                offerId=str(_get(offer, "id", default=vid)),
                vendorId=vid,
                name=vendor_doc.name if vendor_doc else vid,
                country=_vendor_country(vendor_doc),
                sku=str(_get(offer, "vendorSku", "vendor_sku", default="") or ""),
                unit=str(_get(offer, "unit", default="") or ""),
                unitPrice=unit_price,
                currency=str(_get(offer, "currency", default="USD") or "USD"),
                leadTimeDays=lead_days,
                contracted=bool(offer.get("contracted")),
                availabilityStatus=str(
                    _get(offer, "availabilityStatus", "availability_status", default="") or ""
                ),
            )
        )

    return WorkflowDetailDTO(
        id=workflow_id,
        requestId=str(request_id),
        title=str(title),
        requester=str(_get(request, "requester_id", "requesterId", default="unknown")),
        costCenter=str(_get(request, "organization_id", "organizationId", default="—")),
        opened=_format_relative(str(created_at) if created_at else None),
        target=target,
        needBy=str(_get(request, "required_by_date", "requiredByDate", default="—")),
        spec=str(_get(product, "description", default=_get(request, "purpose", default=""))),
        prStatus=pr_status.value,
        phaseDurations={
            "rfq": None,
            "neg": None,
            "po": None,
            "grn": None,
            "inv": None,
            "done": None,
        },
        phaseStatus=phase_status_map(pr_status),
        specDone=spec_done(pr_status),
        currentPhase=pr_status_to_phase_id(pr_status),
        needsAction=needs_action(pr_status),
        actionLabel=action_label(pr_status),
        discoveredVendors=discovered,
        vendors=vendors,
        activity=activity,
        po=state.get(PO_KEY) if isinstance(state.get(PO_KEY), dict) else None,
        grn=state.get(GRN_KEY) if isinstance(state.get(GRN_KEY), dict) else None,
        invoice=state.get(INVOICE_KEY) if isinstance(state.get(INVOICE_KEY), dict) else None,
        selectedVendor=selected if isinstance(selected, dict) else None,
    )


def vendor_thread_rows_from_state(
    workflow_id: str,
    state: dict[str, Any],
    *,
    vendor_names: dict[str, Vendor] | None = None,
) -> list[VendorThreadRowDTO]:
    vendor_names = vendor_names or {}
    request = state.get(REQUEST_KEY) if isinstance(state.get(REQUEST_KEY), dict) else {}
    request_id = str(_get(request, "request_id", "requestId", default=workflow_id))
    created_at = _get(request, "created_at", "createdAt")
    selected = state.get(SELECTED_VENDOR_KEY)
    selected_vendor_id: str | None = None
    if isinstance(selected, dict):
        selected_vendor_id = str(_get(selected, "vendor", default="") or "") or None

    overrides = _thread_overrides(state)
    neg_config = state.get(NEGOTIATION_CONFIG_KEY)
    if not isinstance(neg_config, dict):
        return []

    rows: list[VendorThreadRowDTO] = []
    for vid, cfg in neg_config.items():
        if not isinstance(cfg, dict):
            continue
        rfq_id = str(cfg.get("rfq_id") or "")
        if not rfq_id:
            continue
        vendor_id = str(cfg.get("vendor_id") or vid)
        vendor_doc = vendor_names.get(vendor_id)
        comms = cfg.get("communications")
        comms_list = comms if isinstance(comms, list) else []
        latest = _latest_price_from_communications(comms_list)
        round_val = cfg.get("round")
        thread_status = infer_vendor_thread_status(
            cfg,
            selected_vendor_id=selected_vendor_id,
            override=overrides.get(rfq_id),
        )
        state_label = to_state_label(thread_status)
        done = bool(cfg.get("done")) or thread_status.name in {
            "WALKED_AWAY",
            "AWARDED",
            "REJECTED",
            "EXPIRED",
        }

        rows.append(
            VendorThreadRowDTO(
                id=rfq_id,
                vendorId=vendor_id,
                name=vendor_doc.name if vendor_doc else vendor_id,
                country=_vendor_country(vendor_doc),
                tier="Tier-2",
                pr=request_id,
                workflowId=workflow_id,
                last=_format_relative(str(created_at) if created_at else None),
                state=state_label,
                unread=0,
                msgs=len(comms_list),
                round=int(round_val) if isinstance(round_val, int) else None,
                latestPrice=latest,
                done=done,
            )
        )
    return rows


_NEGOTIATION_MSG_TYPES = frozenset({"RFQ", "QUOTE", "COUNTER_OFFER", "ACCEPT", "WALKAWAY"})
_FULFILLMENT_MSG_TYPES = frozenset(
    {"PO", "PO_ACKNOWLEDGED", "GRN_CREATED", "INVOICE_SUBMITTED", "PROCESS_COMPLETE", "RFQ_CLOSED"}
)


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_money(value: Any, currency: str = "USD") -> str:
    num = _coerce_float(value)
    if num is None:
        return ""
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    return f"{symbol}{num:,.2f}"


def _phase_for(msg_type: str) -> str:
    if msg_type in _NEGOTIATION_MSG_TYPES:
        return "negotiation"
    if msg_type in _FULFILLMENT_MSG_TYPES:
        return "fulfillment"
    return ""


def _message_highlight(msg_type: str, payload: dict[str, Any], currency: str) -> str:
    """One-line summary shown next to each timeline event."""
    p = payload if isinstance(payload, dict) else {}
    item = p.get("item") if isinstance(p.get("item"), dict) else {}

    if msg_type == "RFQ":
        qty = item.get("quantity")
        required_by = p.get("required_by") or p.get("requiredBy")
        bits = []
        if qty is not None:
            bits.append(f"qty {qty}")
        if required_by:
            bits.append(f"need by {required_by}")
        return " · ".join(bits)

    if msg_type in {"QUOTE", "COUNTER_OFFER", "ACCEPT"}:
        unit = _fmt_money(p.get("unit_price") or p.get("unitPrice"), currency)
        total = _fmt_money(p.get("total_price") or p.get("totalPrice"), currency)
        bits = []
        if unit:
            bits.append(f"{unit} / unit")
        if total and total != unit:
            bits.append(f"total {total}")
        if msg_type == "COUNTER_OFFER" and p.get("is_final"):
            bits.append("final")
        return " · ".join(bits)

    if msg_type == "WALKAWAY":
        reason = p.get("reason") or p.get("walkaway_reason")
        return f"reason {reason}" if reason else "walkaway"

    if msg_type == "RFQ_CLOSED":
        outcome = p.get("outcome")
        return str(outcome) if outcome else "rfq closed"

    if msg_type == "PO":
        po = p.get("po_number") or p.get("poNumber")
        total = _fmt_money(p.get("total_amount") or p.get("totalAmount"), currency)
        delivery = p.get("delivery_date") or p.get("deliveryDate")
        bits = []
        if po:
            bits.append(str(po))
        if total:
            bits.append(f"total {total}")
        if delivery:
            bits.append(f"deliver {delivery}")
        return " · ".join(bits)

    if msg_type == "PO_ACKNOWLEDGED":
        po = p.get("po_number") or p.get("poNumber")
        return f"ack {po}" if po else "acknowledged"

    if msg_type == "GRN_CREATED":
        grn = p.get("grn_number") or p.get("grnNumber")
        received = p.get("received_at") or p.get("receivedAt")
        bits = []
        if grn:
            bits.append(str(grn))
        if received:
            bits.append(f"received {str(received)[:10]}")
        return " · ".join(bits)

    if msg_type == "INVOICE_SUBMITTED":
        inv = p.get("invoice_number") or p.get("invoiceNumber")
        total = _fmt_money(p.get("total_amount") or p.get("totalAmount"), currency)
        due = p.get("due_date") or p.get("dueDate")
        bits = []
        if inv:
            bits.append(str(inv))
        if total:
            bits.append(f"total {total}")
        if due:
            bits.append(f"due {due}")
        return " · ".join(bits)

    if msg_type == "PROCESS_COMPLETE":
        bits = [str(p.get(k)) for k in ("po_number", "grn_number", "invoice_number") if p.get(k)]
        return " · ".join(bits)

    return ""


def _build_vendor_summary(
    state: dict[str, Any],
    messages: list[VendorThreadMessageDTO],
) -> VendorThreadSummaryDTO:
    product = state.get("product") if isinstance(state.get("product"), dict) else {}
    currency = str(product.get("currency") or "USD") if isinstance(product, dict) else "USD"

    quoted: float | None = None
    for msg in messages:
        if msg.type == "QUOTE" and quoted is None:
            quoted = _coerce_float(msg.payload.get("unit_price") or msg.payload.get("unitPrice"))
            break

    accepted = _coerce_float(state.get("accepted_price"))
    latest_offer = _coerce_float(state.get("latest_offer_price"))
    last_selling = _coerce_float(state.get("last_selling_price"))

    po = state.get("po") if isinstance(state.get("po"), dict) else {}
    grn = state.get("grn") if isinstance(state.get("grn"), dict) else {}

    invoice_number: str | None = None
    for msg in reversed(messages):
        if msg.type == "INVOICE_SUBMITTED":
            invoice_number = str(msg.payload.get("invoice_number") or "") or None
            break

    # Delivered date = GRN ``received_at`` (actual receipt). Stripped to YYYY-MM-DD.
    delivered_on: str | None = None
    received_at = grn.get("received_at") if grn else None
    if received_at:
        delivered_on = str(received_at)[:10]

    expected_delivery = (
        str(po.get("delivery_date")) if po and po.get("delivery_date") else None
    )

    return VendorThreadSummaryDTO(
        status=str(state.get("status") or ""),
        quotedPrice=quoted,
        acceptedPrice=accepted,
        latestOfferPrice=latest_offer,
        lastSellingPrice=last_selling,
        currency=currency,
        poNumber=(str(po.get("po_number")) if po.get("po_number") else None) if po else None,
        grnNumber=(str(grn.get("grn_number")) if grn.get("grn_number") else None) if grn else None,
        invoiceNumber=invoice_number,
        expectedDelivery=expected_delivery,
        deliveredOn=delivered_on,
    )


def vendor_convo_from_state(
    rfq_id: str,
    state: dict[str, Any],
    *,
    workflow_id: str = "",
    vendor_doc: Vendor | None = None,
    product_doc: Product | None = None,
    events: list[WorkflowEventDoc] | None = None,  # noqa: ARG001 — kept for ABI
) -> VendorConvoDTO:
    """Build the conversation DTO from the vendor session state.

    ``state.communication`` is the source of truth — it carries every envelope
    (negotiation + fulfillment) the vendor processed for this rfq. Workflow
    events are intentionally not used here because they only cover negotiation
    traffic emitted by the buyer's negotiator subagent.
    """
    vendor_id = str(state.get("vendor_id") or "")
    status = str(state.get("status") or "UNKNOWN")
    product = state.get("product") if isinstance(state.get("product"), dict) else {}
    currency = (
        str(product.get("currency") or "USD") if isinstance(product, dict) else "USD"
    )

    messages: list[VendorThreadMessageDTO] = []
    comms = state.get("communication")
    comms_list = comms if isinstance(comms, list) else []
    for entry in comms_list:
        if not isinstance(entry, dict):
            continue
        ts = str(entry.get("timestamp") or "")
        msg_type = str(entry.get("message_type") or entry.get("messageType") or "MSG")
        from_agent = str(entry.get("from_agent") or entry.get("fromAgent") or "")
        to_agent = str(entry.get("to_agent") or entry.get("toAgent") or "")
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        round_raw = entry.get("round")
        try:
            round_value = int(round_raw) if round_raw is not None else None
        except (TypeError, ValueError):
            round_value = None
        messages.append(
            VendorThreadMessageDTO(
                ts=ts[:19].replace("T", " ") if ts else "",
                **{"from": from_agent, "to": to_agent},
                type=msg_type,
                phase=_phase_for(msg_type),
                payload=payload,
                highlight=_message_highlight(msg_type, payload, currency),
                round=round_value,
            )
        )

    summary = _build_vendor_summary(state, messages)

    outcome = status
    if state.get("accepted_price"):
        outcome = f"ACCEPTED @ {state['accepted_price']}"

    product_state = product if isinstance(product, dict) else {}
    product_id = str(product_state.get("id") or "") if product_state else ""
    product_sku = str(product_state.get("sku") or "") if product_state else ""
    if product_doc is not None:
        product_label = product_doc.name or product_sku or product_id
        product_brand = product_doc.brand or ""
        product_type = product_doc.type or ""
        product_id = product_doc.id or product_id
    else:
        product_label = product_sku or product_id
        product_brand = ""
        product_type = ""

    return VendorConvoDTO(
        vendor={
            "id": vendor_id,
            "name": vendor_doc.name if vendor_doc else vendor_id,
            "country": _vendor_country(vendor_doc),
            "tier": "Tier-2",
            "mssa": "active",
        },
        product={
            "id": product_id,
            "name": product_label,
            "sku": product_sku,
            "brand": product_brand,
            "type": product_type,
        },
        pr=workflow_id or rfq_id,
        workflowId=workflow_id,
        rfqId=rfq_id,
        outcome=outcome,
        summary=summary,
        messages=messages,
    )
