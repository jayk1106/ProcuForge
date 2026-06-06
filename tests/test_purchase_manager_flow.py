"""Tests for buyer purchase_manager tools and callbacks (mocked A2A)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from communication.schema import MessageType
from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.state_keys import (
    GRN_KEY,
    INVOICE_KEY,
    INVOICE_VENDOR_ACK_KEY,
    NEGOTIATION_CONFIG_KEY,
    PO_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PROCESS_COMPLETE_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
    PURCHASE_STALL_STREAK_KEY,
    PURCHASE_STEP_SNAPSHOT_KEY,
    RFQ_CLOSED_LOSERS_KEY,
    SELECTED_VENDOR_KEY,
)
from procu_forge_buyer.subagents.purchase_manager.callbacks import (
    purchase_manager_after_agent,
    purchase_manager_before_agent,
)
from procu_forge_buyer.pr_status_transitions import sync_purchase_pr_status_from_acks
from procu_forge_buyer.subagents.purchase_manager.tools import (
    _notify_losing_vendors,
    send_grn_created,
    send_po,
    send_process_complete,
)

_VENDOR_ID = "5fbebce3-8715-4150-8f14-3def51d54208"
_RFQ_ID = "680653bf-88ac-42fc-8bfe-92cd09a1d01b"
_WINNER_ID = "8ba9dcc8-6a12-4c68-8811-b60840d72abd"


class _FakeState(dict):
    """Minimal ADK State stand-in for callback tests."""

    def to_dict(self) -> dict:
        return dict(self)


def _base_state() -> dict:
    return {
        SELECTED_VENDOR_KEY: {"vendor": _VENDOR_ID, "final_price": 30.88, "outcome": "ACCEPTED"},
        NEGOTIATION_CONFIG_KEY: {
            _VENDOR_ID: {
                "rfq_id": _RFQ_ID,
                "product": {
                    "id": "prod-1",
                    "sku": "PI-OFF-0001",
                    "quantity": 1,
                    "currency": "USD",
                    "price": 32.5,
                },
                "communications": [],
            }
        },
        "request": {"required_by_date": "2026-07-03"},
    }


def _state_without_agreed_price() -> dict:
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _VENDOR_ID, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_VENDOR_ID]["product"].pop("price", None)
    state[NEGOTIATION_CONFIG_KEY][_VENDOR_ID]["communications"] = []
    return state


def _tool_context(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


def _po_ack_reply(po_number: str) -> str:
    return json.dumps(
        {
            "message_type": MessageType.PO_ACKNOWLEDGED,
            "payload": {"po_number": po_number},
        }
    )


def _invoice_reply(po_number: str, grn_number: str, invoice_number: str = "INV-TEST") -> str:
    return json.dumps(
        {
            "message_type": MessageType.INVOICE_SUBMITTED,
            "payload": {
                "invoice_number": invoice_number,
                "po_number": po_number,
                "grn_reference": grn_number,
            },
        }
    )


async def test_send_po_no_state_on_vendor_error():
    state = _base_state()
    ctx = _tool_context(state)

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        return_value=json.dumps({"ok": False, "error": "po_validation_failed"}),
    ):
        result = await send_po(ctx)

    assert result["ok"] is False
    assert state.get(PO_KEY, {}).get("po_number")
    assert PO_VENDOR_ACK_KEY not in state


async def test_send_po_sets_ack_on_success():
    state = _base_state()
    ctx = _tool_context(state)

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
    ) as mock_call:
        async def _side_effect(payload, rfq_id):
            env = json.loads(payload)
            return _po_ack_reply(env["payload"]["po_number"])

        mock_call.side_effect = _side_effect
        result = await send_po(ctx)

    assert result["ok"] is True
    assert state.get(PO_KEY, {}).get("po_number")
    assert state.get(PO_VENDOR_ACK_KEY)


async def test_send_grn_no_synthetic_invoice_on_bad_reply():
    state = _base_state()
    state[PO_KEY] = {"po_number": "PO-TEST", "line_items": [{"sku": "PI-OFF-0001", "quantity": 1}]}
    state[PO_VENDOR_ACK_KEY] = {"message_type": "PO_ACKNOWLEDGED"}
    ctx = _tool_context(state)

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        return_value="not json",
    ):
        result = await send_grn_created(ctx)

    assert result["ok"] is False
    assert INVOICE_KEY not in state
    assert INVOICE_VENDOR_ACK_KEY not in state


async def test_send_process_complete_no_state_on_out_of_order():
    state = _base_state()
    state[PO_KEY] = {"po_number": "PO-1"}
    state[GRN_KEY] = {"grn_number": "GRN-1"}
    state[INVOICE_KEY] = {"invoice_number": "INV-1"}
    state[INVOICE_VENDOR_ACK_KEY] = {"message_type": "INVOICE_SUBMITTED"}
    ctx = _tool_context(state)

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        return_value=json.dumps(
            {"ok": False, "error": "process_complete_out_of_order", "current_status": "ACCEPTED"}
        ),
    ):
        result = await send_process_complete(ctx)

    assert result["ok"] is False
    assert PROCESS_COMPLETE_KEY not in state
    assert PROCESS_COMPLETE_VENDOR_ACK_KEY not in state


def test_callback_no_po_ack_transition():
    state = _FakeState({
        PR_STATUS_KEY: PrStatus.PO_ISSUED.value,
        PO_KEY: {"po_number": "PO-1"},
    })
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-1"

    purchase_manager_before_agent(ctx)
    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.PO_ISSUED.value


def test_callback_advances_on_po_vendor_ack():
    state = _FakeState({
        PR_STATUS_KEY: PrStatus.PO_ISSUED.value,
        PO_VENDOR_ACK_KEY: {"message_type": "PO_ACKNOWLEDGED"},
        PURCHASE_STEP_SNAPSHOT_KEY: {},
    })
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-2"

    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value


async def test_send_po_notifies_losing_vendors_in_one_call():
    """send_po should fire RFQ_CLOSED to losers and the PO to the winner in one tool call."""
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {
            "id": "prod-1",
            "sku": "PI-OFF-0001",
            "quantity": 1,
            "currency": "USD",
        },
        "communications": [],
    }
    ctx = _tool_context(state)

    captured: list[dict] = []

    async def _side_effect(payload, rfq_id):
        env = json.loads(payload)
        captured.append(env)
        if env["message_type"] == "RFQ_CLOSED":
            return json.dumps({"ok": True, "message": "RFQ_CLOSED acknowledged"})
        if env["message_type"] == "PO":
            return _po_ack_reply(env["payload"]["po_number"])
        return json.dumps({"ok": False, "error": "unexpected"})

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        result = await send_po(ctx)

    assert result["ok"] is True
    # Both the loser RFQ_CLOSED and the winner PO went out from the same tool call.
    msg_types = [e["message_type"] for e in captured]
    assert "RFQ_CLOSED" in msg_types
    assert "PO" in msg_types
    assert state[RFQ_CLOSED_LOSERS_KEY][_VENDOR_ID] is True
    assert state[PO_VENDOR_ACK_KEY]


async def test_send_po_skips_loser_notification_when_already_notified():
    """If losers were already RFQ_CLOSED in a prior turn, send_po should not re-notify."""
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {"id": "prod-1", "sku": "PI-OFF-0001", "quantity": 1, "currency": "USD"},
        "communications": [],
    }
    state[RFQ_CLOSED_LOSERS_KEY] = {_VENDOR_ID: True}
    ctx = _tool_context(state)

    captured: list[dict] = []

    async def _side_effect(payload, rfq_id):
        env = json.loads(payload)
        captured.append(env)
        return _po_ack_reply(env["payload"]["po_number"])

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        result = await send_po(ctx)

    assert result["ok"] is True
    msg_types = [e["message_type"] for e in captured]
    assert "RFQ_CLOSED" not in msg_types
    assert msg_types == ["PO"]


def test_after_agent_advances_to_po_issued_when_losers_closed():
    state = _FakeState(
        {
            PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value,
            RFQ_CLOSED_LOSERS_KEY: {_VENDOR_ID: True},
            PURCHASE_STEP_SNAPSHOT_KEY: {},
        }
    )
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-auto"

    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.PO_ISSUED.value


def test_sync_advances_to_completed_all_acks_no_rfq_closed():
    """All vendor ack keys set but losers never RFQ_CLOSED — still reaches COMPLETED."""
    state = _base_state()
    state[PR_STATUS_KEY] = PrStatus.VENDOR_SELECTED.value
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = state[NEGOTIATION_CONFIG_KEY][_VENDOR_ID]
    state[RFQ_CLOSED_LOSERS_KEY] = {}
    state[PO_VENDOR_ACK_KEY] = {"message_type": "PO_ACKNOWLEDGED"}
    state[INVOICE_VENDOR_ACK_KEY] = {"message_type": "INVOICE_SUBMITTED"}
    state[PROCESS_COMPLETE_VENDOR_ACK_KEY] = {"message_type": "PROCESS_COMPLETE"}

    assert sync_purchase_pr_status_from_acks(state) is True
    assert state[PR_STATUS_KEY] == PrStatus.COMPLETED.value


def test_sync_unblocks_with_po_ack_only():
    """po_vendor_ack alone unblocks VENDOR_SELECTED without RFQ_CLOSED to losers."""
    state = _base_state()
    state[PR_STATUS_KEY] = PrStatus.VENDOR_SELECTED.value
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = state[NEGOTIATION_CONFIG_KEY][_VENDOR_ID]
    state[PO_VENDOR_ACK_KEY] = {"message_type": "PO_ACKNOWLEDGED"}

    assert sync_purchase_pr_status_from_acks(state) is True
    assert state[PR_STATUS_KEY] == PrStatus.PO_ACKNOWLEDGED.value


async def test_notify_losing_vendors_plain_ok_ack():
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {"id": "prod-1", "sku": "PI-OFF-0001", "quantity": 1, "currency": "USD"},
        "communications": [],
    }

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        return_value=json.dumps({"ok": True, "message": "RFQ_CLOSED acknowledged"}),
    ):
        result = await _notify_losing_vendors(state)

    assert result["ok"] is True
    assert state[RFQ_CLOSED_LOSERS_KEY][_VENDOR_ID] is True


async def test_notify_losing_vendors_empty_reply_retry():
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {"id": "prod-1", "sku": "PI-OFF-0001", "quantity": 1, "currency": "USD"},
        "communications": [],
    }

    call_count = {"n": 0}

    async def _side_effect(payload, rfq_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ""
        return json.dumps({"ok": True, "message": "RFQ_CLOSED acknowledged"})

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        with patch(
            "procu_forge_buyer.subagents.purchase_manager.tools.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await _notify_losing_vendors(state)

    assert call_count["n"] == 2
    assert result["ok"] is True
    assert state[RFQ_CLOSED_LOSERS_KEY][_VENDOR_ID] is True


async def test_send_po_succeeds_when_rfq_closed_fails():
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {"id": "prod-1", "sku": "PI-OFF-0001", "quantity": 1, "currency": "USD"},
        "communications": [],
    }
    ctx = _tool_context(state)

    async def _side_effect(payload, rfq_id):
        env = json.loads(payload)
        if env["message_type"] == "RFQ_CLOSED":
            return ""
        return _po_ack_reply(env["payload"]["po_number"])

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        with patch(
            "procu_forge_buyer.subagents.purchase_manager.tools.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await send_po(ctx)

    assert result["ok"] is True
    assert state[PO_VENDOR_ACK_KEY]
    assert result["rfq_closed"]["ok"] is False
    assert result["rfq_closed"]["all_notified"] is False


def test_after_agent_advances_to_completed_when_all_acks_present():
    """after_agent uses sync helper to chain through to COMPLETED."""
    state = _FakeState(
        {
            PR_STATUS_KEY: PrStatus.VENDOR_SELECTED.value,
            SELECTED_VENDOR_KEY: {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"},
            NEGOTIATION_CONFIG_KEY: _base_state()[NEGOTIATION_CONFIG_KEY],
            RFQ_CLOSED_LOSERS_KEY: {},
            PO_VENDOR_ACK_KEY: {"message_type": "PO_ACKNOWLEDGED"},
            INVOICE_VENDOR_ACK_KEY: {"message_type": "INVOICE_SUBMITTED"},
            PROCESS_COMPLETE_VENDOR_ACK_KEY: {"message_type": "PROCESS_COMPLETE"},
            PURCHASE_STEP_SNAPSHOT_KEY: {},
        }
    )
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = state[NEGOTIATION_CONFIG_KEY][_VENDOR_ID]
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-complete"

    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.COMPLETED.value


def test_stall_guard_escalates_outside_purchase_phase():
    """Stall escalation applies outside purchase-phase statuses, not during PO_ISSUED etc."""
    state = _FakeState({
        PR_STATUS_KEY: PrStatus.NEGOTIATION_COMPLETED.value,
        PURCHASE_STEP_SNAPSHOT_KEY: {},
        PURCHASE_STALL_STREAK_KEY: 1,
    })
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-3"

    purchase_manager_before_agent(ctx)
    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.ESCALATED.value
    assert state[PURCHASE_STALL_STREAK_KEY] == 2


def test_stall_guard_does_not_escalate_during_po_issued():
    state = _FakeState({
        PR_STATUS_KEY: PrStatus.PO_ISSUED.value,
        PURCHASE_STEP_SNAPSHOT_KEY: {},
        PURCHASE_STALL_STREAK_KEY: 1,
    })
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = "sess-stall-exempt"

    purchase_manager_before_agent(ctx)
    purchase_manager_after_agent(ctx)

    assert state[PR_STATUS_KEY] == PrStatus.PO_ISSUED.value
    assert state[PURCHASE_STALL_STREAK_KEY] == 1


async def test_send_po_resends_when_ack_missing():
    """A second send_po call after an unparseable first reply re-sends the same envelope."""
    state = _base_state()
    ctx = _tool_context(state)

    call_count = {"n": 0}
    captured_envelopes: list[dict] = []

    async def _side_effect(payload, rfq_id):
        call_count["n"] += 1
        env = json.loads(payload)
        captured_envelopes.append(env)
        if call_count["n"] == 1:
            return "garbage not json"
        return _po_ack_reply(env["payload"]["po_number"])

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        first = await send_po(ctx)
        assert first["ok"] is False
        first_po_number = state[PO_KEY]["po_number"]
        assert PO_VENDOR_ACK_KEY not in state

        second = await send_po(ctx)

    assert call_count["n"] == 2
    assert second["ok"] is True
    assert state[PO_VENDOR_ACK_KEY]
    # Both attempts used the same po_number — resend, not a new mint.
    assert captured_envelopes[0]["payload"]["po_number"] == first_po_number
    assert captured_envelopes[1]["payload"]["po_number"] == first_po_number


async def test_send_po_errors_when_agreed_price_missing():
    state = _state_without_agreed_price()
    ctx = _tool_context(state)

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
    ) as mock_call:
        result = await send_po(ctx)

    mock_call.assert_not_called()
    assert result["ok"] is False
    assert result["error"] == "agreed_price_unresolved"
    assert PO_KEY not in state


async def test_send_grn_resends_when_invoice_ack_missing():
    """A second send_grn_created call after a garbage first reply resends the same GRN."""
    state = _base_state()
    state[PO_KEY] = {
        "po_number": "PO-RETRY",
        "line_items": [{"sku": "PI-OFF-0001", "quantity": 2}],
    }
    state[PO_VENDOR_ACK_KEY] = {"message_type": "PO_ACKNOWLEDGED"}
    ctx = _tool_context(state)

    call_count = {"n": 0}
    captured: list[dict] = []

    async def _side_effect(payload, rfq_id):
        call_count["n"] += 1
        env = json.loads(payload)
        captured.append(env)
        if call_count["n"] == 1:
            return "garbage"
        return _invoice_reply(
            env["payload"]["po_number"],
            env["payload"]["grn_number"],
        )

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        first = await send_grn_created(ctx)
        assert first["ok"] is False
        first_grn = state[GRN_KEY]["grn_number"]
        assert INVOICE_VENDOR_ACK_KEY not in state

        second = await send_grn_created(ctx)

    assert call_count["n"] == 2
    assert second["ok"] is True
    assert state[INVOICE_VENDOR_ACK_KEY]
    assert captured[0]["payload"]["grn_number"] == first_grn
    assert captured[1]["payload"]["grn_number"] == first_grn


async def test_send_po_skips_winner_when_loser_notification_fails():
    """If a loser returns ok:false, send_po should still attempt the PO but mark loser un-notified."""
    state = _base_state()
    state[SELECTED_VENDOR_KEY] = {"vendor": _WINNER_ID, "final_price": 30.88, "outcome": "ACCEPTED"}
    state[NEGOTIATION_CONFIG_KEY][_WINNER_ID] = {
        "rfq_id": "rfq-winner",
        "product": {"id": "prod-1", "sku": "PI-OFF-0001", "quantity": 1, "currency": "USD"},
        "communications": [],
    }
    ctx = _tool_context(state)

    async def _side_effect(payload, rfq_id):
        env = json.loads(payload)
        if env["message_type"] == "RFQ_CLOSED":
            return json.dumps({"ok": False, "error": "vendor_closed_failure"})
        return _po_ack_reply(env["payload"]["po_number"])

    with patch(
        "procu_forge_buyer.subagents.purchase_manager.tools.call_vendor",
        new_callable=AsyncMock,
        side_effect=_side_effect,
    ):
        result = await send_po(ctx)

    # PO went through; loser remains un-notified so future turns will retry it.
    assert result["ok"] is True
    assert state.get(RFQ_CLOSED_LOSERS_KEY, {}).get(_VENDOR_ID) is not True
    assert state[PO_VENDOR_ACK_KEY]


def test_purchase_progress_uses_grn_to_invoice_block():
    """build_purchase_progress should expose a single grn_to_invoice step."""
    from procu_forge_buyer.subagents.purchase_manager.tools import build_purchase_progress

    state = _base_state()
    state[PR_STATUS_KEY] = PrStatus.PO_ACKNOWLEDGED.value
    state[PO_KEY] = {"po_number": "PO-X"}
    state[PO_VENDOR_ACK_KEY] = {"message_type": "PO_ACKNOWLEDGED"}

    progress = build_purchase_progress(state)
    assert "grn_to_invoice" in progress["steps"]
    assert "grn" not in progress["steps"]
    assert "invoice" not in progress["steps"]
    # next_tool was removed — the LLM decides via the instruction now.
    assert "next_tool" not in progress


def test_instruction_provider_drives_full_flow():
    """The InstructionProvider embeds the progress and mandates chained tool calls."""
    from unittest.mock import MagicMock

    from procu_forge_buyer.subagents.purchase_manager.agent import (
        purchase_manager_instruction,
    )

    state = _base_state()
    state[PR_STATUS_KEY] = PrStatus.VENDOR_SELECTED.value
    ctx = MagicMock()
    ctx.state = state

    rendered = purchase_manager_instruction(ctx)
    # All three send tools must be mentioned so the model can chain through.
    assert "send_po" in rendered
    assert "send_grn_created" in rendered
    assert "send_process_complete" in rendered
    # The retired single-step tool name should not leak back into the prompt.
    assert "send_rfq_closed_to_losing_vendors" not in rendered
    # The current pr_status must appear in the embedded progress JSON.
    assert "VENDOR_SELECTED" in rendered
    # Behaviour-affecting copy: imperative chain language.
    assert "MUST" in rendered
    assert "single turn" in rendered or "same turn" in rendered
