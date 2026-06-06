# Cloud Run + Vercel Deployment

Operational runbook for deploying ProcuForge to **Google Cloud Run** (API + internal vendor A2A) and **Vercel** (Next.js frontend).

**Quick path:** configure [`.env.production.example`](../.env.production.example) → one-time [`setup_cloud_run_once.sh`](../scripts/setup_cloud_run_once.sh) → every update [`deploy_cloud_run.sh`](../scripts/deploy_cloud_run.sh).

For Agent Engine (buyer + vendor reasoning engines), see [deployment.md](./deployment.md).

For secrets, CORS, and auth details, see [production_setup_guide.md](./production_setup_guide.md).

---

## Architecture

```
Vercel (Next.js)
    │  HTTPS + WSS (direct to Cloud Run)
    ▼
Cloud Run — single container
    ├── FastAPI (public, port $PORT)
    ├── vendor_server.py (127.0.0.1:8001, loopback only)
    └── Buyer Runner (BackgroundTasks)
            │
            └── A2A HTTP → localhost:8001
                    │
                    ▼
            Vertex AI Agent Engine (buyer + vendor sessions)
            Firestore (products, workflow index, events)
```

| Component | Host |
|---|---|
| Next.js UI | Vercel |
| FastAPI + WebSockets | Cloud Run |
| Vendor A2A server | Cloud Run (loopback, not public) |
| Buyer/vendor agent execution | Cloud Run (`Runner` in-process) |
| Buyer/vendor session storage | Vertex AI Agent Engine |
| Product/workflow metadata | Firestore |

---

## Configuration file

All deploy settings live in **`.env.production`** (gitignored). Copy the template once:

```bash
cp .env.production.example .env.production
```

The file has two sections:

| Section | Purpose |
|---|---|
| **Deploy tooling** | GCP project, image name, Cloud Run scaling — used by scripts only |
| **Cloud Run runtime env** | Injected into the container on every deploy (`API_ENV`, reasoning engines, CORS, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, etc.) |

`JWT_SECRET` and `ADMIN_PASSWORD_HASH` in `.env.production` are the **actual secret values** (same names as [`api/config.py`](../api/config.py)). They are injected via `--env-vars-file` on deploy. Keep `.env.production` gitignored.

---

## One-time setup

Do this once per GCP project (or when creating a new environment).

### 1. Deploy Agent Engine

```bash
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor
```

Reasoning engine IDs are written to `logs/*_deployment_metadata.json`. The deploy script can read them automatically when `SYNC_REASONING_ENGINES_FROM_LOGS=true` in `.env.production`.

### 2. Configure `.env.production`

```bash
cp .env.production.example .env.production
```

Edit at minimum:

- `GCP_PROJECT_ID`, `GCP_REGION`, `SERVICE_ACCOUNT`
- `WORKFLOW_DEFAULT_USER_ID`, `WORKFLOW_DEFAULT_ORGANIZATION_ID`
- `ADMIN_USER_ID`, `ADMIN_ORG_ID`
- `API_CORS_ORIGINS` — your Vercel URL (after first Vercel deploy)

Set `SYNC_REASONING_ENGINES_FROM_LOGS=true` to auto-fill buyer/vendor engine IDs from the log metadata files.

### 3. Generate auth secrets

```bash
uv run python scripts/generate_auth_secrets.py
```

Copy `JWT_SECRET` and `ADMIN_PASSWORD_HASH` into `.env.production`.

### 4. Run the one-time setup script

Creates APIs, Artifact Registry, service account, and IAM:

```bash
./scripts/setup_cloud_run_once.sh
```

If `.env.production` does not exist, the script copies from `.env.production.example` and exits — edit the file, then re-run.

### 5. Deploy Vercel (one-time project setup)

1. Import repo in Vercel, root directory **`web`**
2. Set `NEXT_PUBLIC_API_URL` to your Cloud Run URL (after first API deploy, or update after)
3. Note the Vercel URL and set `API_CORS_ORIGINS` in `.env.production`
4. Redeploy API: `./scripts/deploy_cloud_run.sh`

---

## Every-time deploy (API updates)

After code or env changes, run **one command** from the repo root:

```bash
./scripts/deploy_cloud_run.sh
```

This script:

1. Loads `.env.production`
2. Optionally syncs reasoning engine IDs from log metadata
3. Validates required variables
4. `docker build` → `docker push` → `gcloud run deploy`
5. Injects runtime env from `.env.production` via `--env-vars-file` (includes `JWT_SECRET`, `ADMIN_PASSWORD_HASH`)
6. Runs `/health` and `/health/ready` checks (disable with `VERIFY_AFTER_DEPLOY=false`)

### Script options

```bash
./scripts/deploy_cloud_run.sh --help
./scripts/deploy_cloud_run.sh --dry-run          # print actions only
./scripts/deploy_cloud_run.sh --skip-build       # push + deploy existing local image
./scripts/deploy_cloud_run.sh --skip-push        # deploy image already in registry
./scripts/deploy_cloud_run.sh --no-verify        # skip post-deploy curl checks
./scripts/deploy_cloud_run.sh --env-file /path/to/.env.production
```

### Local Docker smoke test (optional, before Cloud Run)

```bash
docker build -t procuforge-api:local .
docker run --rm -p 8080:8080 \
  --env-file .env.production \
  -e PORT=8080 \
  procuforge-api:local

curl -s http://localhost:8080/health
curl -s http://localhost:8080/health/ready
```

Local runs still need GCP credentials for Firestore/Vertex (ADC or mounted key — do not bake keys into the image).

---

## Container layout

| File | Purpose |
|---|---|
| [`Dockerfile`](../Dockerfile) | Python 3.13 image, `uv sync`, runs [`scripts/start.sh`](../scripts/start.sh) |
| [`.dockerignore`](../.dockerignore) | Excludes `.env`, `web/`, etc. |
| [`scripts/start.sh`](../scripts/start.sh) | Vendor on loopback → poll agent card → FastAPI on `$PORT` |
| [`scripts/deploy_cloud_run.sh`](../scripts/deploy_cloud_run.sh) | Build, push, deploy |
| [`scripts/setup_cloud_run_once.sh`](../scripts/setup_cloud_run_once.sh) | One-time GCP setup |
| [`.env.production.example`](../.env.production.example) | Config template |

Port **8001** is loopback-only inside the container — not exposed publicly.

---

## Cloud Run runtime environment

These variables are set from `.env.production` on every deploy (not passed on the command line):

| Variable | Required | Description |
|---|---|---|
| `API_ENV` | Yes | `production` |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Yes | e.g. `us-central1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes | `True` |
| `BUYER_REASONING_ENGINE` | Yes | Agent Engine resource name |
| `VENDOR_REASONING_ENGINE` | Yes | Agent Engine resource name |
| `VENDOR_A2A_AGENT_CARD_URL` | Yes | `http://127.0.0.1:8001/.well-known/agent-card.json` |
| `VENDOR_SERVER_HOST` | Yes | `127.0.0.1` |
| `VENDOR_SERVER_PORT` | Yes | `8001` |
| `WORKFLOW_DEFAULT_USER_ID` | Yes | ADK session user id |
| `WORKFLOW_DEFAULT_ORGANIZATION_ID` | Yes | Default org for workflows |
| `API_CORS_ORIGINS` | Yes | Exact Vercel URL(s), comma-separated |
| `JWT_SECRET` | Yes | From `generate_auth_secrets.py` |
| `ADMIN_PASSWORD_HASH` | Yes | Bcrypt hash from `generate_auth_secrets.py` |
| `ADMIN_USER_ID`, `ADMIN_ORG_ID` | Recommended | Match Firestore user/org docs |

Optional: `ADMIN_USER_NAME`, `ADMIN_ORG_NAME`, etc. — see [authentication.md](./authentication.md).

Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run — use the attached service account.

---

## Post-deploy verification

The deploy script runs health checks automatically. Manual checks:

```bash
API_URL=$(gcloud run services describe procuforge-api \
  --region=us-central1 --format='value(status.url)')

curl -s "${API_URL}/health"
curl -s "${API_URL}/health/ready"

curl -s -c /tmp/pf-cookie.txt -X POST "${API_URL}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"password":"YOUR_PASSWORD"}'

curl -s -b /tmp/pf-cookie.txt "${API_URL}/api/v1/workflow/list"
```

**UI:** Vercel → login → start workflow → WebSocket updates on flow detail.

---

## Troubleshooting

### Deploy script fails validation

- `Missing required variables` — fill blanks in `.env.production`
- `Set API_CORS_ORIGINS to your real Vercel URL` — replace the placeholder
- `Set BUYER_REASONING_ENGINE...` — deploy Agent Engine or enable `SYNC_REASONING_ENGINES_FROM_LOGS=true`

### `/health/ready` returns 503

| Cause | Fix |
|---|---|
| Vendor A2A unreachable | Check `VENDOR_REASONING_ENGINE`; Cloud Run logs for vendor startup |
| Firestore unreachable | Service account needs `roles/datastore.user` |
| Missing reasoning engine env | Run Agent Engine deploy; sync metadata |

### CORS errors

- `API_CORS_ORIGINS` must match the browser origin exactly (`https://…`, no trailing slash)
- Redeploy after changing: `./scripts/deploy_cloud_run.sh`

### Login works but API returns 401

- `NEXT_PUBLIC_API_URL` on Vercel must match Cloud Run hostname
- Cookie is on the API domain — frontend uses `credentials: 'include'` (already in `api-client.ts`)

### WebSocket issues

- Session affinity enabled by default (`CLOUD_RUN_SESSION_AFFINITY=true`)
- WS uses ticket auth — confirm `POST /auth/ws-ticket` returns 200 when logged in

---

## Out of scope

- CI/CD pipeline
- Custom domain + shared cookie domain
- Cloud Tasks for runs exceeding 60-minute timeout
- Redis pub/sub for multi-instance WebSocket fanout
