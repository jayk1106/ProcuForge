# Production Setup Guide

Step-by-step checklist for deploying ProcuForge to **Cloud Run + Vercel**. Use this document when configuring secrets, environment variables, and CORS before your first production deploy.

**Deploy workflow:**

1. One-time: `./scripts/setup_cloud_run_once.sh`
2. Every update: `./scripts/deploy_cloud_run.sh`
3. Config file: `.env.production` (copy from [`.env.production.example`](../.env.production.example))

For the full runbook, see [cloud_run_deployment.md](./cloud_run_deployment.md).

For Agent Engine-only deployment, see [deployment.md](./deployment.md).

---

## Overview of changes in this repo

These code changes support the production layout:

| Change | File(s) | Why |
|---|---|---|
| Single container startup | `Dockerfile`, `scripts/start.sh` | FastAPI + vendor A2A on loopback in one Cloud Run service |
| Deploy automation | `scripts/deploy_cloud_run.sh`, `scripts/setup_cloud_run_once.sh` | One command deploy; env in `.env.production` |
| Production env validation | `api/main.py` | Fail fast if reasoning engines or auth secrets are missing |
| Readiness probe | `api/routers/health.py` | Cloud Run checks Firestore + vendor A2A before routing traffic |
| Client-side auth gate | `web/src/components/auth/AuthGate.tsx` | Cross-origin cookie lives on API domain, not Vercel |
| Removed middleware cookie check | `web/src/middleware.ts` deleted | Cookie on Cloud Run domain was invisible to Vercel middleware |

---

## Step 1 — Deploy Agent Engine (if not already done)

```bash
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor
```

Copy the reasoning engine resource names:

| Agent | File | Env var |
|---|---|---|
| Buyer | `logs/procu-forge-buyer_deployment_metadata.json` → `remote_agent_engine_id` | `BUYER_REASONING_ENGINE` |
| Vendor | `logs/procu-forge-vendor_deployment_metadata.json` → `remote_agent_engine_id` | `VENDOR_REASONING_ENGINE` |

Example (your IDs will differ):

```bash
BUYER_REASONING_ENGINE=projects/192679313906/locations/us-central1/reasoningEngines/9115807364065263616
VENDOR_REASONING_ENGINE=projects/192679313906/locations/us-central1/reasoningEngines/2617113101769637888
```

---

## Step 2 — Generate auth secrets

```bash
uv run python scripts/generate_auth_secrets.py
```

Copy the output into **`.env.production`** (not git):

```bash
JWT_SECRET='...'
ADMIN_PASSWORD_HASH='...'
```

---

## Step 3 — Create `.env.production`

```bash
cp .env.production.example .env.production
```

Edit `.env.production` — the deploy script reads **everything** from this file (no long `gcloud` commands).

### Deploy tooling section (scripts only)

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | `ratelx-ai` |
| `GCP_REGION` | `us-central1` |
| `CLOUD_RUN_SERVICE` | `procuforge-api` |
| `SERVICE_ACCOUNT` | `procuforge-run@ratelx-ai.iam.gserviceaccount.com` |
| `JWT_SECRET` | From `generate_auth_secrets.py` |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash from `generate_auth_secrets.py` |
| `SYNC_REASONING_ENGINES_FROM_LOGS` | `true` — auto-fill engine IDs from `logs/` |

### Cloud Run runtime section (injected into container)

| Variable | Your value |
|---|---|
| `API_ENV` | `production` |
| `GOOGLE_CLOUD_PROJECT` | same as `GCP_PROJECT_ID` |
| `GOOGLE_CLOUD_LOCATION` | e.g. `us-central1` |
| `BUYER_REASONING_ENGINE` | (from Step 1, or auto-sync) |
| `VENDOR_REASONING_ENGINE` | (from Step 1, or auto-sync) |
| `WORKFLOW_DEFAULT_USER_ID` | your user UUID |
| `WORKFLOW_DEFAULT_ORGANIZATION_ID` | your org UUID |
| `API_CORS_ORIGINS` | Vercel URL (Step 5) |
| `ADMIN_USER_ID`, `ADMIN_ORG_ID` | match Firestore seed data |

`JWT_SECRET` and `ADMIN_PASSWORD_HASH` in `.env.production` are injected into Cloud Run on each deploy under the same names as [`api/config.py`](../api/config.py).

---

## Step 4 — One-time GCP setup + optional local Docker test

```bash
./scripts/setup_cloud_run_once.sh
```

Optional smoke test before first Cloud Run deploy:

```bash
docker build -t procuforge-api:local .
docker run --rm -p 8080:8080 --env-file .env.production -e PORT=8080 procuforge-api:local
curl http://localhost:8080/health/ready
```

If readiness fails, read the `detail` array in the 503 response.

**Note:** Local Docker still needs GCP credentials for Firestore and Vertex (ADC or mounted key — do not bake keys into the image).

---

## Step 5 — Deploy Cloud Run, then Vercel

### API (every code or env change)

```bash
./scripts/deploy_cloud_run.sh
```

First run performs build + push + deploy + health checks. After deploy, note the service URL:

```bash
gcloud run services describe procuforge-api --region=us-central1 --format='value(status.url)'
```

### Vercel

1. Root directory **`web`**
2. Set `NEXT_PUBLIC_API_URL` to the Cloud Run URL above
3. Deploy and note the Vercel URL
4. Set `API_CORS_ORIGINS` in `.env.production` to that exact URL
5. Redeploy API: `./scripts/deploy_cloud_run.sh`

Multiple origins (preview + production), comma-separated, no spaces:

```bash
API_CORS_ORIGINS=https://procuforge.vercel.app,https://procuforge-git-main-you.vercel.app
```

---

## Step 6 — CORS configuration

CORS is configured in [`api/main.py`](../api/main.py) via `API_CORS_ORIGINS`.

Rules:

- Must be **explicit origins** in production (wildcard `*` is rejected at startup).
- Must include `https://` and match the browser origin exactly.
- Required because the auth cookie uses `credentials: 'include'` cross-origin.

Verify in Cloud Run logs after deploy:

```
cors.configured origins=['https://your-app.vercel.app'] allow_credentials=True
```

---

## Authentication in production

### How it works (Vercel + Cloud Run)

```
Browser on vercel.app
    │
    ├── POST cloud-run.app/api/v1/auth/login  → Set-Cookie on cloud-run.app
    ├── GET  cloud-run.app/api/v1/auth/me     → cookie sent (credentials: include)
    └── WSS  cloud-run.app/ws/...?ticket=...  → ticket from POST /auth/ws-ticket
```

The session cookie (`pf_session`) is stored for the **Cloud Run domain**, not Vercel.

### Why middleware was removed

The old [`middleware.ts`](../web/src/middleware.ts) checked for `pf_session` on the Vercel domain. In production that cookie never appears there, so every page redirected to `/login` even after a successful login.

### What replaced it

[`AuthGate`](../web/src/components/auth/AuthGate.tsx) runs client-side:

1. Calls `GET /auth/me` with `credentials: 'include'`
2. Shows a loading state while checking
3. Redirects to `/login?next=…` if unauthenticated

Real JWT verification still happens in FastAPI on every API and WebSocket request.

### Local development

Unchanged: run API on `:8000`, Next.js on `:3000`, set in `web/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Default `API_CORS_ORIGINS` is `http://localhost:3000`.

---

## What not to commit

| File | Reason |
|---|---|
| `.env` | Local dev secrets |
| `.env.production` | Production deploy config (project ids, CORS, engine names) |
| Service account JSON keys | Use Cloud Run service account instead |
| `web/.env.local` | Local overrides |

`.env` and `.env.production` are gitignored — never commit `JWT_SECRET` or `ADMIN_PASSWORD_HASH`.

---

## Pre-deploy checklist

- [ ] Buyer + vendor Agent Engine deployed; IDs copied
- [ ] `JWT_SECRET` and `ADMIN_PASSWORD_HASH` set in `.env.production`
- [ ] Cloud Run service account has Firestore + Vertex access
- [ ] `.env.production` filled from `.env.production.example`
- [ ] `./scripts/setup_cloud_run_once.sh` completed
- [ ] `./scripts/deploy_cloud_run.sh` succeeds (health + ready → 200)
- [ ] Vercel deployed with `NEXT_PUBLIC_API_URL`
- [ ] `API_CORS_ORIGINS` updated to Vercel URL and API redeployed
- [ ] Login + workflow start tested end-to-end

---

## Optional future improvements

### Custom domain + shared cookie

If you later use `app.yourdomain.com` (Vercel) and `api.yourdomain.com` (Cloud Run), you can set `Domain=.yourdomain.com` on the session cookie so middleware-style checks work again. Requires a small change to [`api/routers/auth.py`](../api/routers/auth.py).

### CI/CD

Automate `docker build`, `gcloud run deploy`, and Vercel deploy on merge to `main`.

### Horizontal scaling

WebSocket fanout is in-memory per instance. Before scaling beyond one instance, add Redis pub/sub or keep `--max-instances 1` with session affinity.

---

## Quick reference links

- [cloud_run_deployment.md](./cloud_run_deployment.md) — build, deploy, verify, troubleshoot
- [deployment.md](./deployment.md) — Agent Engine only
- [authentication.md](./authentication.md) — auth API reference
- [firestore_setup.md](./firestore_setup.md) — Firestore configuration
