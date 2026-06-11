"""Tests for purchase_manager state access (ADK State vs plain dict)."""

from __future__ import annotations

from google.adk.sessions.state import State

from procu_forge_buyer.state_keys import NEGOTIATION_CONFIG_KEY, SELECTED_VENDOR_KEY
from procu_forge_buyer.subagents.purchase_manager.tools import get_vendor_config

_VENDOR_ID = "8ba9dcc8-6a12-4c68-8811-b60840d72abd"
_RFQ_ID = "7b2ae7df-3fa1-49ae-950e-1e7f5cd8e433"


def _sample_state_value() -> dict:
    return {
        SELECTED_VENDOR_KEY: {"vendor": _VENDOR_ID, "final_price": 30.88},
        NEGOTIATION_CONFIG_KEY: {
            _VENDOR_ID: {
                "rfq_id": _RFQ_ID,
                "product": {"id": "prod-1", "sku": "SKU-1", "quantity": 1},
            }
        },
    }


def testget_vendor_config_with_plain_dict():
    result = get_vendor_config(_sample_state_value())
    assert result == (_VENDOR_ID, _sample_state_value()[NEGOTIATION_CONFIG_KEY][_VENDOR_ID])


def testget_vendor_config_with_adk_state():
    adk_state = State(_sample_state_value(), {})
    result = get_vendor_config(adk_state)
    assert isinstance(result, tuple)
    vendor_id, config = result
    assert vendor_id == _VENDOR_ID
    assert config["rfq_id"] == _RFQ_ID


def test_dict_adk_state_raises_key_error():
    """Regression: dict(State) must not be used — it iterates with integer keys."""
    adk_state = State(_sample_state_value(), {})
    try:
        dict(adk_state)  # noqa: C408
        raised = False
    except KeyError:
        raised = True
    assert raised
