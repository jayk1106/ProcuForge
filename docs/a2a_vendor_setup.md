# Vendor A2A agent (local mock)

This repo includes **procu_forge_vendor**: an ADK agent that responds to RFQs with synthetic quotes and negotiation. It is exposed over the **Agent-to-Agent (A2A)** protocol when you run the ADK API server with `--a2a`.

**procu_forge_buyer**’s negotiator uses `RemoteA2aAgent` to talk to that vendor over HTTP.

## Prerequisites

- Python env with dependencies installed: `uv sync` (includes `google-adk[a2a]`).
- Same Vertex / GenAI env as the buyer (see root `.env` and `procu_forge_buyer/.env`).

## 1. Start the vendor A2A server

From the **repository root** (the parent of both agent folders):

```bash
uv run adk api_server --a2a --host 127.0.0.1 --port 8000 .
```

Notes:

- `agents_dir` must be the **parent directory** that contains `procu_forge_vendor/` (and `procu_forge_buyer/`). Using `.` from the repo root is correct.
- A2A RPC base: `http://127.0.0.1:8000/a2a/procu_forge_vendor`
- Agent card (well-known): `http://127.0.0.1:8000/a2a/procu_forge_vendor/.well-known/agent.json`  
  (path from `AGENT_CARD_WELL_KNOWN_PATH` in the A2A SDK)

## 2. Run the buyer

In a **second** terminal, with the vendor server still running:

```bash
uv run python main.py
```

Or use your FastAPI workflow as configured.

## 3. Override vendor URL

If the vendor runs on another host/port:

```bash
export VENDOR_A2A_AGENT_CARD_URL="http://127.0.0.1:9000/a2a/procu_forge_vendor/.well-known/agent.json"
```

(Append the well-known path that matches your server’s `--port` and route.)

## Limitations (mock)

- Quotes and floors are **deterministic synthetic** math, not Firestore.
- No authentication on the local A2A endpoint.
- Both agents need network access to Vertex (or your configured model backend).
