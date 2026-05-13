"""Vendor A2A server with explicit in-memory session management.

Exposes procu_forge_vendor as an A2A Starlette app using ADK's to_a2a utility.
Sessions are stored in-process (InMemorySessionService) — state does not
survive a server restart. Suitable for local development and testing.

Run:
    uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

Or as a script (uses uvicorn programmatically):
    uv run python vendor_server.py

Environment overrides:
    VENDOR_SERVER_HOST  (default: 127.0.0.1)
    VENDOR_SERVER_PORT  (default: 8001)
"""

from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from procu_forge_vendor.agent import root_agent

load_dotenv()

_HOST = os.getenv("VENDOR_SERVER_HOST", "127.0.0.1")
_PORT = int(os.getenv("VENDOR_SERVER_PORT", "8001"))

_runner = Runner(
    app_name=root_agent.name,
    agent=root_agent,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
    memory_service=InMemoryMemoryService(),
    credential_service=InMemoryCredentialService(),
)

app = to_a2a(
    root_agent,
    host=_HOST,
    port=_PORT,
    runner=_runner,
)

if __name__ == "__main__":
    uvicorn.run(app, host=_HOST, port=_PORT)
