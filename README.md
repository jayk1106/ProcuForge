# ProcuForge

ADK-based procurement agents.

## Agents

- **procu_forge_buyer** — Buyer orchestrator (vendor search, negotiation, decision, PO).
- **procu_forge_vendor** — Vendor-side quotes and negotiation (synthetic pricing).

## Vendor A2A (local)

The buyer negotiator talks to the vendor over **A2A**. Start the vendor API server from the repo root, then run the buyer. See **[docs/a2a_vendor_setup.md](docs/a2a_vendor_setup.md)**.

Quick start:

```bash
# Terminal 1 — vendor A2A endpoint
uv run adk api_server --a2a --host 127.0.0.1 --port 8000 .

# Terminal 2 — buyer (example)
uv run python main.py
```

## Setup

```bash
uv sync
```

Configure Vertex / credentials via `.env` (see existing variables in the repo).
