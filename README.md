# ProcuForge

ADK-based procurement agents.

## Agents

- **procu_forge_buyer** — Buyer orchestrator (vendor search, negotiation, decision, PO).
- **procu_forge_vendor** — Vendor-side quotes and negotiation (synthetic pricing).

## Vendor A2A (local)

The buyer negotiator talks to the vendor over **A2A**. Start the vendor API server from the repo root, then run the buyer. See **[docs/a2a_vendor_setup.md](docs/a2a_vendor_setup.md)**.

Quick start (custom runner with in-memory sessions):

```bash
# Terminal 1 — vendor A2A server (in-memory sessions)
uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

# Terminal 2 — buyer
uv run python main.py
```

See **[docs/a2a_vendor_setup.md](docs/a2a_vendor_setup.md)** for the legacy `adk api_server --a2a` approach and all configuration options.

## Setup

```bash
uv sync
```

Configure Vertex / credentials via `.env` (see existing variables in the repo).

## Deployment

End-to-end deploy guide (Agent Engine + Cloud Run + Vercel), covering first-time setup and every subsequent redeploy: **[docs/deployment_guide.md](docs/deployment_guide.md)**.
