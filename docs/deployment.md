# Agent Engine Deployment

This document covers deploying the two ProcuForge agents to **Vertex AI Agent Engine** (reasoning engines) and the configuration each deployment requires.

- **Buyer** — `procu_forge_buyer.agent.root_agent` (procurement orchestrator loop)
- **Vendor** — `procu_forge_vendor.agent.root_agent` (quotes + negotiation)

Both share one deployment package, with a thin entry script per agent:

```
deployment/
  config.py              # env resolution + validation (build_config)
  agent_engine_app.py    # AgentEngineApp + deploy_agent_engine_app(...)
  deploy_buyer.py        # entry point for the buyer
  deploy_vendor.py       # entry point for the vendor
  utils/
    gcs.py               # create_bucket_if_not_exists
    tracing.py           # CloudTraceLoggingSpanExporter
    typing.py            # Feedback model (register_feedback)
```

---

## 1. Configuration (environment variables)

Configuration is read from the repo-root `.env` (loaded automatically) or the process environment. Set these in `.env`:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Yes | — | Target Google Cloud project. Falls back to `GOOGLE_PROJECT_ID`, then `gcloud` ADC default. |
| `GOOGLE_CLOUD_LOCATION` | No | `us-central1` | Vertex AI region. Falls back to `GOOGLE_BUCKET_REGION`. |
| `GOOGLE_CLOUD_STAGING_BUCKET` | **Yes** | — | Staging bucket for Agent Engine packaging. Name only (no `gs://`). **Not yet in `.env` — add it.** |
| `MODEL` | No | `gemini-2.5-flash` | Vertex publisher model id for all ADK agents (see `adk_vertex_model/`). |
| `REQUIREMENTS_FILE` | No | `.requirements.txt` | Pinned dependency file shipped with the deployment. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes | — | Already `True` in `.env`; routes GenAI calls through Vertex. |
| `GOOGLE_APPLICATION_CREDENTIALS` | For local deploy | — | Path to a service-account key, or use ADC (`gcloud auth application-default login`). |

The current `.env` already defines `GOOGLE_CLOUD_PROJECT`, `GOOGLE_PROJECT_ID`, `GOOGLE_BUCKET_REGION`, and `GOOGLE_GENAI_USE_VERTEXAI`. **You must add `GOOGLE_CLOUD_STAGING_BUCKET`** before deploying:

```bash
# .env
GOOGLE_CLOUD_STAGING_BUCKET=ratelx-ai-agent-staging
```

### Per-agent settings (in code, not env)

Each deploy script hardcodes the values that must differ between the two agents:

| Setting | Buyer | Vendor |
|---|---|---|
| Display name | `procu-forge-buyer` | `procu-forge-vendor` |
| Extra packages | `./procu_forge_buyer`, `./communication`, `./db` | `./procu_forge_vendor`, `./communication`, `./db` |
| Artifacts bucket | `<project>-procu-forge-buyer-logs-data` | `<project>-procu-forge-vendor-logs-data` |

`extra_packages` covers every local package each agent imports (the agent package itself plus the shared `communication` and `db` packages).

---

## 2. One-time setup

1. **Authenticate** (Application Default Credentials):

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

2. **Enable the required APIs:**

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com
```

3. **Create the staging bucket** (the per-agent artifacts bucket is created automatically by the deploy script):

```bash
gcloud storage buckets create gs://ratelx-ai-agent-staging --location=us-central1
```

4. **Install dependencies and pin requirements:**

```bash
uv sync
uv export --no-hashes > .requirements.txt
```

Re-run the `uv export` step whenever `pyproject.toml` dependencies change, so the deployed environment matches local.

---

## 3. Deploy

Run from the **repository root** (paths in `extra_packages` are relative to it):

```bash
# Buyer
uv run python -m deployment.deploy_buyer

# Vendor
uv run python -m deployment.deploy_vendor
```

Each run is idempotent: the script looks up an existing Agent Engine by display name and **updates** it if found, otherwise **creates** a new one.

### Outputs

| Artifact | Location |
|---|---|
| Deployment metadata (buyer) | `logs/procu-forge-buyer_deployment_metadata.json` |
| Deployment metadata (vendor) | `logs/procu-forge-vendor_deployment_metadata.json` |
| Artifacts bucket | `gs://<project>-procu-forge-<agent>-logs-data` |

Each metadata file records the `remote_agent_engine_id` (resource name), timestamp, project, location, and artifacts bucket.

---

## 4. Included features

- **Cloud Logging** — the deployed app logs through Cloud Logging.
- **Cloud Trace tracing** — spans are exported via `CloudTraceLoggingSpanExporter`; oversized attributes (large prompts/responses) are offloaded to Cloud Logging with a pointer left in the span to stay under Cloud Trace's attribute size limit.
- **Feedback logging** — `register_feedback` accepts a `Feedback` payload (`score`, `text`, `invocation_id`, `user_id`) and writes it as a structured log entry.
- **GCS artifact service** — agent artifacts are persisted to the per-agent artifacts bucket.

---

## 5. Known follow-up: buyer-to-vendor A2A connectivity

The buyer's negotiator/purchase-manager call the vendor through `call_vendor()` in [procu_forge_buyer/a2a_client.py](../procu_forge_buyer/a2a_client.py), which resolves an **A2A agent card over HTTP** at `VENDOR_A2A_AGENT_CARD_URL` (defaults to `http://127.0.0.1:8001/.well-known/agent-card.json`, served by [vendor_server.py](../vendor_server.py)).

A Vertex AI Agent Engine reasoning engine **does not serve that `.well-known` agent-card endpoint over plain HTTP**. So deploying the vendor to Agent Engine does not, by itself, make a deployed buyer able to reach it via the current A2A client.

To run the full buyer-to-vendor flow in production you still need one of:

- Keep the vendor reachable as an A2A HTTP server (e.g. host `vendor_server.py` on Cloud Run) and point `VENDOR_A2A_AGENT_CARD_URL` at that URL, **or**
- Adapt `a2a_client.py` to invoke the deployed vendor Agent Engine directly (by resource name) instead of resolving an HTTP agent card.

This wiring is intentionally out of scope for the deployment scripts here.
