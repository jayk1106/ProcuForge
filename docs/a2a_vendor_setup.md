# Vendor A2A server

`procu_forge_vendor` is an ADK agent that responds to RFQs with synthetic quotes and negotiation. It is exposed as an **A2A** HTTP server so `procu_forge_buyer`'s negotiator can reach it via `RemoteA2aAgent`.

Two ways to start the server are supported:

| Approach | Session storage | Entry point |
|---|---|---|
| **Custom runner** (recommended) | `InMemorySessionService` (in-process) | `vendor_server.py` |
| ADK API server (legacy) | ADK default (also in-memory by default) | `adk api_server --a2a` |

---

## Prerequisites

```bash
uv sync          # installs google-adk[a2a] and all other deps
```

Configure Vertex / GenAI credentials in `.env` (same as the buyer — see existing variables in the repo).

---

## Option A — Custom runner (recommended)

The custom runner (`vendor_server.py`) builds the `Runner` explicitly with `InMemorySessionService` and exposes the agent using ADK's `to_a2a()` utility. This is the transparent, code-first approach.

### Endpoints (custom runner)

| Purpose | URL |
|---|---|
| Agent card (primary) | `http://127.0.0.1:8001/.well-known/agent-card.json` |
| Agent card (legacy alias) | `http://127.0.0.1:8001/.well-known/agent.json` |
| A2A JSON-RPC | `http://127.0.0.1:8001/` |

### Start the vendor server

```bash
# Terminal 1 — vendor A2A server
uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001
```

Or run directly as a script:

```bash
uv run python vendor_server.py
```

### Run the buyer

```bash
# Terminal 2 — buyer (vendor server must already be running)
uv run python main.py
```

No extra environment variables are required. The buyer's default `VENDOR_A2A_AGENT_CARD_URL` already points to `http://127.0.0.1:8001/.well-known/agent.json`, which is the legacy alias served by the custom runner.

### Override host/port

```bash
export VENDOR_SERVER_HOST=0.0.0.0
export VENDOR_SERVER_PORT=9001
uv run uvicorn vendor_server:app --host 0.0.0.0 --port 9001
```

Tell the buyer where to find the new card:

```bash
export VENDOR_A2A_AGENT_CARD_URL="http://0.0.0.0:9001/.well-known/agent.json"
```

### Suppress experimental-feature warnings

`to_a2a()` is marked experimental in the current ADK release and logs a warning on startup. Suppress it with:

```bash
export ADK_SUPPRESS_A2A_EXPERIMENTAL_FEATURE_WARNINGS=true
```

---

## Option B — ADK API server (legacy)

Runs all agents discovered under the repo root via the ADK CLI. The vendor is mounted at the `/a2a/procu_forge_vendor` path prefix.

### Endpoints (ADK API server)

| Purpose | URL |
|---|---|
| Agent card | `http://127.0.0.1:8000/a2a/procu_forge_vendor/.well-known/agent.json` |
| A2A JSON-RPC | `http://127.0.0.1:8000/a2a/procu_forge_vendor` |

### Start

```bash
# Terminal 1 — vendor (and buyer) agents via ADK CLI
uv run adk api_server --a2a --host 127.0.0.1 --port 8000 .
```

`agents_dir` must be the **parent directory** that contains `procu_forge_vendor/` (`.` from the repo root is correct).

### Run the buyer

Because the ADK API server uses a different URL prefix, you must override the buyer's default:

```bash
export VENDOR_A2A_AGENT_CARD_URL="http://127.0.0.1:8000/a2a/procu_forge_vendor/.well-known/agent.json"
uv run python main.py
```

---

## Session behaviour

`InMemorySessionService` keeps all sessions in the server process's heap.

- Sessions **do not survive a server restart**. Every time you restart the vendor server, negotiation history is lost.
- This is intentional for local development. A persistence-backed service (e.g. `VertexAiSessionService`) can be swapped in by editing `vendor_server.py`.

---

## Limitations (mock)

- Quotes and floor prices are **deterministic synthetic math** — no Firestore or external pricing data.
- No authentication on the local A2A endpoint.
- Both agents need network access to Vertex (or your configured model backend).
