"""Vendor A2A server with rfq_id-based session threading.

Exposes procu_forge_vendor as an A2A Starlette app.  A custom request_converter
maps ``rfq_id`` from the procurement message body to the ADK session_id so the
vendor agent accumulates context across all turns of a single negotiation thread
(RFQ → counter-offer → accept / walk-away) instead of starting a fresh session
on every A2A call.

On the first RFQ for a new rfq_id the converter also seeds ``state_delta`` with
the canonical vendor state structure so tools and the callback start with a
complete skeleton from turn 1:

    {
        "vendor_id":    <from envelope>,
        "rfq_id":       <from envelope>,
        "round":        0,
        "product":      { id, sku, currency, unit, price, quantity },
        "communication": [ <RFQ envelope> ]
    }

Sessions are stored in a local SQLite file via DatabaseSessionService, so
state survives server restarts (suitable for local development / testing).

Run:
    uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

Or as a script:
    uv run python vendor_server.py

Environment overrides:
    VENDOR_SERVER_HOST  (default: 127.0.0.1)
    VENDOR_SERVER_PORT  (default: 8001)
    VENDOR_SESSION_DB_URL   (full SQLAlchemy URL, optional)
    VENDOR_SESSION_DB_PATH  (sqlite file path, default: ./data/vendor_sessions.db)
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from dotenv import load_dotenv
from google.adk.a2a.converters.part_converter import A2APartToGenAIPartConverter
from google.adk.a2a.converters.request_converter import (
    AgentRunRequest,
    convert_a2a_request_to_agent_run_request,
)
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from starlette.applications import Starlette
from a2a.server.agent_execution.context import RequestContext

from procu_forge_vendor.agent import root_agent
from procu_forge_vendor.state_keys import (
    COMMUNICATION_KEY,
    PRODUCT_KEY,
    ROUND_KEY,
    RFQ_ID_KEY,
    VENDOR_ID_KEY,
)

load_dotenv()

_LOG = logging.getLogger(__name__)

_HOST = os.getenv("VENDOR_SERVER_HOST", "127.0.0.1")
_PORT = int(os.getenv("VENDOR_SERVER_PORT", "8001"))


def _build_session_service() -> DatabaseSessionService:
    """Create a DB-backed ADK session service (local sqlite by default)."""
    db_url = os.getenv("VENDOR_SESSION_DB_URL", "").strip()

    if not db_url:
        db_path_raw = os.getenv("VENDOR_SESSION_DB_PATH", "./data/vendor_sessions.db")
        db_path = Path(db_path_raw).expanduser().resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{db_path}"

    _LOG.info("vendor session storage configured  db_url=%s", db_url)
    return DatabaseSessionService(db_url=db_url)

# ── shared runner ─────────────────────────────────────────────────────────────

_runner = Runner(
    app_name=root_agent.name,
    agent=root_agent,
    artifact_service=InMemoryArtifactService(),
    session_service=_build_session_service(),
    memory_service=InMemoryMemoryService(),
    credential_service=InMemoryCredentialService(),
)


# ── message parsing helpers ───────────────────────────────────────────────────

def _parse_envelope(request: RequestContext) -> dict[str, Any] | None:
    """Extract and JSON-parse the first text part of the A2A message."""
    if not (request.message and request.message.parts):
        return None
    for part in request.message.parts:
        try:
            body = json.loads(part.root.text)
            if isinstance(body, dict):
                return body
        except (AttributeError, TypeError, json.JSONDecodeError, ValueError):
            continue
    return None


def _initial_state_from_rfq(envelope: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical vendor state skeleton from an incoming RFQ envelope.

    Only called when message_type == 'RFQ' and the session is brand-new.
    The product.price / sku / unit fields are stubs — the quote agent's
    get_vendor_product_details tool fills them in from the catalog on turn 1.
    """
    item: dict[str, Any] = (envelope.get("payload") or {}).get("item") or {}
    return {
        VENDOR_ID_KEY: envelope.get("vendor_id", ""),
        RFQ_ID_KEY: envelope.get("rfq_id", ""),
        ROUND_KEY: 0,
        PRODUCT_KEY: {
            "id": item.get("product_id") or item.get("id", ""),
            "sku": item.get("sku", ""),
            "currency": item.get("currency", "USD"),
            "unit": item.get("unit", "unit"),
            "price": float(item.get("unit_price") or 0),
            "quantity": int(item.get("quantity") or 1),
        },
        COMMUNICATION_KEY: [envelope],   # seed with the RFQ itself
    }


# ── custom request converter ──────────────────────────────────────────────────

def rfq_request_converter(
    request: RequestContext,
    part_converter: A2APartToGenAIPartConverter,
) -> AgentRunRequest:
    """Route each A2A turn to the vendor session identified by rfq_id.

    Session routing:
        session_id = rfq_id   (from message envelope)
        user_id    = "vendor_<rfq_id>"

    State seeding (first RFQ turn only):
        state_delta is populated with the full vendor state skeleton so the
        quote agent and callback have a complete starting point without needing
        to re-parse the raw message.  Subsequent turns (counter, accept) carry
        no state_delta — state is maintained by tools.

    Falls back to the default context_id-based routing when rfq_id is absent.
    """
    base = convert_a2a_request_to_agent_run_request(request, part_converter)
    envelope = _parse_envelope(request)

    if not envelope:
        _LOG.debug("rfq_request_converter: no JSON envelope, using default routing")
        return base

    rfq_id = envelope.get("rfq_id")
    if not rfq_id:
        _LOG.debug("rfq_request_converter: no rfq_id in envelope, using default routing")
        return base

    rfq_id = str(rfq_id)
    message_type = str(envelope.get("message_type") or "")

    # Seed state only on the opening RFQ so we don't overwrite tool-written state
    # on counter-offer / accept turns.
    state_delta: dict[str, Any] | None = None
    if message_type == "RFQ":
        state_delta = _initial_state_from_rfq(envelope)
        _LOG.info(
            "rfq_request_converter: RFQ seed  rfq_id=%s product_id=%s qty=%s",
            rfq_id,
            state_delta[PRODUCT_KEY].get("id"),
            state_delta[PRODUCT_KEY].get("quantity"),
        )
    else:
        _LOG.debug(
            "rfq_request_converter: %s turn  rfq_id=%s session_id=%s",
            message_type,
            rfq_id,
            rfq_id,
        )

    return AgentRunRequest(
        user_id=f"vendor_{rfq_id}",
        session_id=rfq_id,
        new_message=base.new_message,
        run_config=base.run_config,
        state_delta=state_delta,
    )


# ── A2A executor + request handler ───────────────────────────────────────────

_executor = A2aAgentExecutor(
    runner=_runner,
    config=A2aAgentExecutorConfig(request_converter=rfq_request_converter),
)

_task_store = InMemoryTaskStore()
_push_config_store = InMemoryPushNotificationConfigStore()

_request_handler = DefaultRequestHandler(
    agent_executor=_executor,
    task_store=_task_store,
    push_config_store=_push_config_store,
)


# ── Starlette app with async agent-card build ─────────────────────────────────

@asynccontextmanager
async def _lifespan(app: Starlette):
    rpc_url = f"http://{_HOST}:{_PORT}/"
    agent_card = await AgentCardBuilder(agent=root_agent, rpc_url=rpc_url).build()
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=_request_handler,
    )
    a2a_app.add_routes_to_app(app)
    _LOG.info("vendor A2A server ready  url=%s", rpc_url)
    yield


app = Starlette(lifespan=_lifespan)


if __name__ == "__main__":
    uvicorn.run(app, host=_HOST, port=_PORT)
