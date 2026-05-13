"""Vendor A2A server with rfq_id-based session threading.

Exposes procu_forge_vendor as an A2A Starlette app.  A custom request_converter
maps ``rfq_id`` from the procurement message body to the ADK session_id so the
vendor agent accumulates context across all turns of a single negotiation thread
(RFQ → counter-offer → accept / walk-away) instead of starting a fresh session
on every A2A call.

Sessions are stored in-process (InMemorySessionService) — state does not
survive a server restart.  Suitable for local development and testing.

Run:
    uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

Or as a script (uses uvicorn programmatically):
    uv run python vendor_server.py

Environment overrides:
    VENDOR_SERVER_HOST  (default: 127.0.0.1)
    VENDOR_SERVER_PORT  (default: 8001)
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

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
from google.adk.sessions import InMemorySessionService
from starlette.applications import Starlette
from a2a.server.agent_execution.context import RequestContext

from procu_forge_buyer.callbacks import _session_state_dict
from procu_forge_vendor.agent import root_agent

load_dotenv()

_LOG = logging.getLogger(__name__)

_HOST = os.getenv("VENDOR_SERVER_HOST", "127.0.0.1")
_PORT = int(os.getenv("VENDOR_SERVER_PORT", "8001"))

# ── shared runner ─────────────────────────────────────────────────────────────

_runner = Runner(
    app_name=root_agent.name,
    agent=root_agent,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
    memory_service=InMemoryMemoryService(),
    credential_service=InMemoryCredentialService(),
)


# ── custom request converter ──────────────────────────────────────────────────

def _extract_rfq_id(request: RequestContext) -> str | None:
    """Parse rfq_id from the first JSON text part of the A2A message."""
    if not (request.message and request.message.parts):
        return None
    for part in request.message.parts:
        try:
            text = part.root.text
            body = json.loads(text)
            print("body", body)
            rfq_id = body.get("rfq_id")
            if rfq_id:
                return str(rfq_id)
        except (AttributeError, TypeError, json.JSONDecodeError, ValueError):
            continue
    return None


def rfq_request_converter(
    request: RequestContext,
    part_converter: A2APartToGenAIPartConverter,
) -> AgentRunRequest:
    """Map rfq_id from the message body to session_id for deterministic threading.

    When the buyer sends any procurement message (RFQ, counter-offer, accept,
    walk-away), the envelope always contains ``rfq_id``.  Using that as the ADK
    session_id means every turn of the same negotiation lands in the same vendor
    session — giving the agent full conversation history — regardless of which
    A2A ``context_id`` the buyer supplied.

    Falls back to the default converter (context_id → session_id) when rfq_id
    cannot be extracted (e.g. non-JSON or missing field).
    """
    base = convert_a2a_request_to_agent_run_request(request, part_converter)

    rfq_id = _extract_rfq_id(request)
    print("rfq_id", rfq_id)
    if not rfq_id:
        _LOG.debug(
            "rfq_request_converter: no rfq_id found, using default session_id=%s",
            base.session_id,
        )
        return base

    _LOG.debug(
        "rfq_request_converter: rfq_id=%s → session_id=%s (was %s)",
        rfq_id,
        rfq_id,
        base.session_id,
    )
    return AgentRunRequest(
        user_id=f"vendor_{rfq_id}",
        session_id=rfq_id,
        new_message=base.new_message,
        run_config=base.run_config,
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
