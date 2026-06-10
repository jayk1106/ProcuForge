"""Escalation notifier subagent: sends one transactional email via Mailgun MCP.

Wired into ``pr_router`` as an ``AgentTool`` so the buyer LLM decides when to
escalate and composes the recipient/subject/body itself (reading from the
pre-resolved state keys populated by ``resolve_escalation_recipient``).

The agent's only tool is the Mailgun MCP toolset; the instruction constrains it
to a single ``send_email`` call per invocation. The Node ``@mailgun/mcp-server``
process is spawned over stdio by ADK's ``McpToolset``.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from adk_vertex_model import vertex_flash_llm

from .callbacks import after_send_email_callback

ESCALATION_NOTIFIER_INSTRUCTION = """
You are **escalation_notifier**. Your only job is to send ONE transactional
email by calling the Mailgun MCP tool ``send_email`` exactly once with the
fields supplied in the invocation prompt.

## Rules

1. Parse the JSON payload from the user message. It contains:
   - ``to`` — single recipient email address.
   - ``subject`` — email subject line.
   - ``text`` — plain-text body.
   - ``html`` — optional HTML body (omit the argument if not present).
   - ``from`` — sender email (set ``from`` to this exact value).
2. Call ``send_email`` exactly once with those arguments. Do NOT call any other
   Mailgun tool (no ``get_logs``, ``query_metrics``, ``get_domain``, etc.).
3. After the tool returns, reply with a one-line acknowledgement summarizing
   whether the send succeeded. Do not invent message ids.
4. If the payload is missing ``to`` or ``subject`` or ``text``, reply with a
   one-line error and do not call any tool.
"""


def _mailgun_env() -> dict[str, str]:
    env: dict[str, str] = {}
    api_key = os.environ.get("MAILGUN_API_KEY", "").strip()
    if api_key:
        env["MAILGUN_API_KEY"] = api_key
    region = os.environ.get("MAILGUN_API_REGION", "").strip()
    if region:
        env["MAILGUN_API_REGION"] = region
    return env


def _build_mailgun_toolset() -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@mailgun/mcp-server"],
                env=_mailgun_env(),
            ),
            timeout=30,
        ),
    )


escalation_notifier_agent = Agent(
    name="escalation_notifier_agent",
    description=(
        "Sends a single escalation email via the Mailgun MCP server. Called by "
        "pr_router as an AgentTool when escalation_pending_notify is set and "
        "the escalation has not yet been emailed."
    ),
    instruction=ESCALATION_NOTIFIER_INSTRUCTION,
    model=vertex_flash_llm(),
    tools=[_build_mailgun_toolset()],
    after_tool_callback=after_send_email_callback,
)


__all__ = ["escalation_notifier_agent"]
