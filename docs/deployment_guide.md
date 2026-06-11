# ProcuForge Deployment Guide

Single, end-to-end guide for deploying ProcuForge. Covers **first-time setup** (everything from a fresh GCP project) and **subsequent redeploys** (what to run after a code or config change).

There are three runtime surfaces:

| Surface | What runs there | Tooling |
|---|---|---|
| Vertex AI Agent Engine | Buyer + vendor ADK reasoning engines (session state) | `deployment/deploy_buyer.py`, `deployment/deploy_vendor.py` |
| Google Cloud Run | FastAPI + WebSockets + vendor A2A loopback (single container) | `scripts/setup_cloud_run_once.sh`, `scripts/deploy_cloud_run.sh` |
| Vercel | Next.js frontend (`web/`) | Vercel dashboard / `vercel` CLI |

For deeper reference material see [`deployment.md`](./deployment.md) (Agent Engine internals), [`cloud_run_deployment.md`](./cloud_run_deployment.md) (Cloud Run runbook), and [`production_setup_guide.md`](./production_setup_guide.md) (auth and CORS background).

---

## Prerequisites

Install once on your workstation:

- `gcloud` CLI (logged in to the target Google account)
- `docker` (Docker Desktop on macOS — the deploy script forces `linux/amd64` builds)
- `python3` (used by the deploy helpers)
- `uv` (Python package manager — `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Vercel account with the repo connected (only needed for the frontend)

You also need:

- A Google Cloud project with billing enabled
- Owner or equivalent IAM on that project (for the one-time IAM bindings)

---

# Part A — First-time deployment

Follow these steps in order on a fresh project. Each step is idempotent, so it is safe to re-run if you make a mistake.

## Step 1. Authenticate to GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

ADC (`application-default login`) is what the Agent Engine deploy scripts use to talk to Vertex AI from your laptop.

## Step 2. Install Python dependencies

From the repo root:

```bash
uv sync
uv export --no-hashes > .requirements.txt
```

`.requirements.txt` is the pinned list shipped with each Agent Engine deployment. Re-export it any time `pyproject.toml` changes.

## Step 3. Create `.env` (Agent Engine deploy config)

The Agent Engine deploy scripts read from the repo-root `.env`. Set at minimum:

```bash
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_STAGING_BUCKET=your-agent-engine-staging-bucket
GOOGLE_GENAI_USE_VERTEXAI=True
```

The staging bucket name is a global GCS bucket name (no `gs://`). Pick something unique, e.g. `myorg-procuforge-staging`.

## Step 4. Enable APIs and create the Agent Engine staging bucket

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com

gcloud storage buckets create gs://your-agent-engine-staging-bucket --location=us-central1
```

Per-agent artifacts buckets (`<project>-procu-forge-buyer-logs-data`, `<project>-procu-forge-vendor-logs-data`) are created automatically by the Agent Engine deploy script — you do not create them.

## Step 5. Deploy buyer + vendor to Agent Engine

```bash
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor
```

Each command takes several minutes. On success the resource names are written to:

- `logs/procu-forge-buyer_deployment_metadata.json`
- `logs/procu-forge-vendor_deployment_metadata.json`

Keep these files — the Cloud Run deploy script reads `remote_agent_engine_id` from them automatically (see Step 9).

## Step 6. Create `.env.production` (Cloud Run deploy config)

```bash
cp .env.production.example .env.production
```

Edit `.env.production` and fill in:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | Your project id |
| `GCP_REGION` | e.g. `us-central1` |
| `SERVICE_ACCOUNT` | `procuforge-run@<project>.iam.gserviceaccount.com` (created in Step 7) |
| `GOOGLE_CLOUD_PROJECT` | Same as `GCP_PROJECT_ID` |
| `GOOGLE_CLOUD_LOCATION` | Same as `GCP_REGION` |
| `WORKFLOW_DEFAULT_USER_ID`, `WORKFLOW_DEFAULT_ORGANIZATION_ID` | UUIDs for the default workflow owner |
| `ADMIN_USER_ID`, `ADMIN_ORG_ID` | UUIDs matching your Firestore seed data |
| `API_CORS_ORIGINS` | Leave the placeholder for now — you will set it after Vercel deploy in Step 11 |
| `SYNC_REASONING_ENGINES_FROM_LOGS` | Leave as `true` so engine IDs auto-sync from `logs/` |

Leave `JWT_SECRET` and `ADMIN_PASSWORD_HASH` placeholders — Step 8 fills them.

## Step 7. Run the Cloud Run one-time setup

```bash
./scripts/setup_cloud_run_once.sh
```

This enables the Cloud Run / Artifact Registry / Firestore / Cloud Build APIs, creates the Artifact Registry repo and the runtime service account, and binds `roles/aiplatform.user` + `roles/datastore.user`. Idempotent — re-running it is safe.

## Step 8. Generate auth secrets

```bash
uv run python scripts/generate_auth_secrets.py
```

Copy the printed `JWT_SECRET` and `ADMIN_PASSWORD_HASH` into `.env.production`. These are the actual secret values; the deploy script injects them into Cloud Run on every deploy.

## Step 9. Deploy Cloud Run for the first time

```bash
./scripts/deploy_cloud_run.sh
```

The script:

1. Loads `.env.production`.
2. Syncs `BUYER_REASONING_ENGINE` / `VENDOR_REASONING_ENGINE` from `logs/*_deployment_metadata.json`.
3. Validates required variables (fails fast if anything is missing).
4. `docker build --platform linux/amd64` → `docker push` → `gcloud run deploy`.
5. Runs `/health` and `/health/ready` against the deployed URL.

On success it prints the service URL. You can also fetch it with:

```bash
gcloud run services describe procuforge-api \
  --region=us-central1 --format='value(status.url)'
```

## Step 10. Deploy Vercel (first time)

In the Vercel dashboard:

1. Import the GitHub repo.
2. Set **Root Directory** to `web`.
3. Framework preset **Next.js**; leave **Output Directory** blank (do not set `public`).
4. Environment variable: `NEXT_PUBLIC_API_URL=<Cloud Run URL from Step 9>`.
5. Deploy and note the Vercel URL (e.g. `https://procuforge.vercel.app`).

## Step 11. Wire CORS and redeploy Cloud Run

Edit `.env.production`:

```bash
API_CORS_ORIGINS=https://procuforge.vercel.app
```

Multiple origins (preview + production) are comma-separated with no spaces. Then redeploy:

```bash
./scripts/deploy_cloud_run.sh
```

## Step 12. Smoke-test the system

```bash
API_URL=$(gcloud run services describe procuforge-api \
  --region=us-central1 --format='value(status.url)')

curl -s "${API_URL}/health"
curl -s "${API_URL}/health/ready"
```

Both should return 200. Then open the Vercel URL in a browser, log in with the admin password, and run a workflow end-to-end.

---

# Part B — Subsequent deploys

What you run depends on what changed. Each scenario below is the full command set — no extra setup needed.

## Scenario 1. API or Python code change (`api/`, `procu_forge_buyer/`, `procu_forge_vendor/`, etc.) without dependency changes

```bash
./scripts/deploy_cloud_run.sh
```

That's it. The script rebuilds the image, pushes, and updates the Cloud Run service in place. The Cloud Run service URL stays the same.

## Scenario 2. Buyer or vendor agent logic change (anything imported by the deployed `root_agent`)

You need to update **both** Agent Engine and Cloud Run, because the buyer/vendor reasoning engines are deployed separately from the FastAPI container.

```bash
# Update only the agent(s) you actually changed
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor

# Then redeploy the API
./scripts/deploy_cloud_run.sh
```

Both Agent Engine deploys are idempotent: the script looks up the existing engine by display name and calls `.update()` instead of creating a new one. **The reasoning engine resource name (`projects/.../reasoningEngines/<id>`) stays the same across updates** — you do not get new IDs each time, and you do not need to edit `.env.production`. The `logs/*_deployment_metadata.json` files are overwritten and the deploy script picks the same IDs back up via `SYNC_REASONING_ENGINES_FROM_LOGS=true`.

## Scenario 3. Dependency change in `pyproject.toml`

Re-pin the requirements lock before deploying anything:

```bash
uv sync
uv export --no-hashes > .requirements.txt
```

Then deploy whichever surface(s) the dependency affects (typically both):

```bash
uv run python -m deployment.deploy_buyer
uv run python -m deployment.deploy_vendor
./scripts/deploy_cloud_run.sh
```

## Scenario 4. Frontend change (`web/`)

Vercel rebuilds automatically when you push to the connected branch. No Cloud Run redeploy needed unless you also changed CORS origins.

## Scenario 5. CORS / env var change in `.env.production`

```bash
./scripts/deploy_cloud_run.sh
```

The script always re-injects the full env file via `--env-vars-file`, so any change to `.env.production` is picked up by a normal redeploy.

## Scenario 6. Rotating `JWT_SECRET` or `ADMIN_PASSWORD_HASH`

```bash
uv run python scripts/generate_auth_secrets.py   # paste new values into .env.production
./scripts/deploy_cloud_run.sh
```

All active user sessions are invalidated by a `JWT_SECRET` rotation — users will have to log in again.

---

## Useful deploy-script flags

```bash
./scripts/deploy_cloud_run.sh --dry-run        # print actions, run nothing
./scripts/deploy_cloud_run.sh --skip-build     # reuse local image tag
./scripts/deploy_cloud_run.sh --skip-push      # image already in Artifact Registry
./scripts/deploy_cloud_run.sh --no-verify      # skip post-deploy curl checks
./scripts/deploy_cloud_run.sh --env-file PATH  # use an alternate env file
```

---

## Verifying any deploy

```bash
API_URL=$(gcloud run services describe procuforge-api \
  --region=us-central1 --format='value(status.url)')

curl -s "${API_URL}/health"          # liveness — container is up
curl -s "${API_URL}/health/ready"    # readiness — Firestore + vendor A2A reachable
```

If `/health/ready` returns 503, the JSON `detail` field tells you which dependency failed.

---

## FAQ

**Do reasoning engine IDs change when I redeploy the buyer or vendor?**
No. The resource name is set on first `create()` and stays the same on every `update()`. `BUYER_REASONING_ENGINE` / `VENDOR_REASONING_ENGINE` in `.env.production` only need to be set once (or auto-synced from `logs/`).

**Does the Cloud Run service URL change when I redeploy?**
No. `gcloud run deploy` updates the existing service in place. The URL is fixed for the lifetime of the service.

**Do I need to re-run `setup_cloud_run_once.sh` when I redeploy?**
No. Only run it on a fresh project, or if you delete the Artifact Registry repo / service account. It is idempotent if you do re-run it.

**What if I create a brand-new GCP project?**
Restart from Step 1. Reasoning engine IDs, the Cloud Run service URL, and the Artifact Registry path will all be new.

**Where are deployment artifacts stored?**
- Agent Engine staging tarballs: `gs://<GOOGLE_CLOUD_STAGING_BUCKET>`
- Per-agent runtime artifacts: `gs://<project>-procu-forge-{buyer,vendor}-logs-data`
- API container image: `<region>-docker.pkg.dev/<project>/procuforge/api:latest`

---

## Troubleshooting pointers

| Symptom | Where to look |
|---|---|
| `Missing required variables` on `deploy_cloud_run.sh` | Fill the blank(s) in `.env.production` reported by the script |
| `Set API_CORS_ORIGINS to your real Vercel URL` | Replace the `your-app.vercel.app` placeholder |
| `Set BUYER_REASONING_ENGINE...` | Run `deploy_buyer.py` / `deploy_vendor.py`, or set `SYNC_REASONING_ENGINES_FROM_LOGS=true` |
| `/health/ready` returns 503 | See [`cloud_run_deployment.md`](./cloud_run_deployment.md#health-ready-returns-503) |
| CORS error in browser | `API_CORS_ORIGINS` must match the browser origin exactly (`https://`, no trailing slash) — then redeploy |
| Login works but API returns 401 | `NEXT_PUBLIC_API_URL` on Vercel must match the Cloud Run hostname |

For everything else, see [`cloud_run_deployment.md`](./cloud_run_deployment.md) (troubleshooting section) and [`production_setup_guide.md`](./production_setup_guide.md) (auth and CORS background).
