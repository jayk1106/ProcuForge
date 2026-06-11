# ProcuForge

Autonomous procurement powered by collaborating AI agents. An end-to-end procurement ecosystem where buyer and vendor agents negotiate, decide, and execute purchasing workflows.

![Architecture](./docs/diagram.png)

For the agent-by-agent walkthrough see [`docs/architecture.md`](./docs/architecture.md).

---

## What's in this repo

| Path | Purpose |
|---|---|
| `procu_forge_buyer/` | Buyer multi-agent system (vendor search, negotiator, decision, purchase manager, workflow QA) |
| `procu_forge_vendor/` | Vendor multi-agent system (quote, negotiation, purchase) |
| `communication/` | Shared A2A message envelope and schema helpers |
| `schema/communication.json` | JSON Schema for every buyer-vendor message type |
| `api/` | FastAPI backend (HTTP + WebSocket) consumed by the Next.js UI |
| `vendor_server.py` | Standalone A2A HTTP server for the vendor agent (runs on `127.0.0.1:8001`) |
| `main.py` | CLI entry point that runs the buyer agent against a Vertex AI session |
| `db/` | Firestore client + repositories |
| `web/` | Next.js 15 frontend |
| `deployment/` | Vertex AI Agent Engine deploy scripts |
| `scripts/` | Cloud Run deploy + one-time setup scripts |
| `docs/` | Architecture, deployment, communication, and auth reference |

---

## Prerequisites

Install once on your workstation:

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node 20+** and **npm** (only for the `web/` frontend)
- **gcloud CLI**, authenticated against the target Google Cloud project
- A **Google Cloud project** with Firestore (Native mode), Vertex AI, and Cloud Storage enabled

---

## Setup

```bash
# 1. Install Python deps
uv sync

# 2. Authenticate to GCP (Application Default Credentials)
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# 3. Create .env in the repo root
cp .env.production.example .env   # or hand-craft a minimal .env
```

Minimum `.env` for local development:

```bash
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True

# Required for main.py (CLI buyer runner) and api/main.py in non-dev mode.
# Obtain by deploying buyer + vendor to Agent Engine (see Deployment below).
BUYER_REASONING_ENGINE=projects/.../reasoningEngines/...
VENDOR_REASONING_ENGINE=projects/.../reasoningEngines/...

# Vendor A2A endpoint the buyer's negotiator calls over HTTP
VENDOR_A2A_AGENT_CARD_URL=http://127.0.0.1:8001/.well-known/agent-card.json
```

See [`docs/firestore_setup.md`](./docs/firestore_setup.md) for Firestore configuration details.

---

## Running locally

The buyer talks to the vendor over A2A HTTP. Start the vendor server first, then the buyer or the API.

### Option A — CLI buyer (one-shot RFQ via `main.py`)

```bash
# Terminal 1 — vendor A2A server (in-memory sessions)
uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

# Terminal 2 — buyer CLI
uv run python main.py
```

`main.py` creates a Vertex AI session, sends a hard-coded request ("Buy me 10 macbook air m1"), and streams agent events to stdout.

To override the vendor server host/port, set `VENDOR_SERVER_HOST` / `VENDOR_SERVER_PORT` and point the buyer at the new card via `VENDOR_A2A_AGENT_CARD_URL`.

### Option B — Full stack (FastAPI + Next.js)

```bash
# Terminal 1 — vendor A2A server
uv run uvicorn vendor_server:app --host 127.0.0.1 --port 8001

# Terminal 2 — FastAPI backend
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 — Next.js frontend
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Then open <http://localhost:3000>. Generate an admin password hash and set `JWT_SECRET` / `ADMIN_PASSWORD_HASH` in `.env` for login (see [`docs/authentication.md`](./docs/authentication.md)).

```bash
uv run python scripts/generate_auth_secrets.py
```

---

## Testing

```bash
uv run pytest                       # full test suite
uv run pytest tests/path/to/test_x.py   # single file
```

---

## Deployment

End-to-end deploy (Agent Engine + Cloud Run + Vercel), covering first-time setup and every subsequent redeploy: **[`docs/deployment_guide.md`](./docs/deployment_guide.md)**.

Quick reference for the most common redeploys:

```bash
# API code change → rebuild + push + deploy
./scripts/deploy_cloud_run.sh

# Buyer or vendor agent logic change → update Agent Engine, then API
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor
./scripts/deploy_cloud_run.sh

# Dependency change → re-pin requirements before deploying
uv sync
uv export --no-hashes > .requirements.txt
```

---

## Documentation index

| Doc | What it covers |
|---|---|
| [`docs/architecture.md`](./docs/architecture.md) | High-level system diagram and component overview |
| [`docs/deployment_guide.md`](./docs/deployment_guide.md) | Single source of truth for deploying Agent Engine + Cloud Run + Vercel |
| [`docs/buyer_vendor_communication_reference.md`](./docs/buyer_vendor_communication_reference.md) | Buyer ↔ vendor message envelope and per-type payload schemas |
| [`docs/authentication.md`](./docs/authentication.md) | Single-user admin auth (cookie + JWT + WS ticket) |
| [`docs/firestore_setup.md`](./docs/firestore_setup.md) | Firestore client configuration, ADC, and the emulator |
| [`docs/request_status.md`](./docs/request_status.md) | All 21 `PrStatus` values with frontend meaning |
