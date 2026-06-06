#!/usr/bin/env bash
# One-time GCP setup for ProcuForge Cloud Run deployment.
#
# Usage:
#   cp .env.production.example .env.production   # edit values first
#   ./scripts/setup_cloud_run_once.sh
#
# Creates (idempotent where possible):
#   - Required GCP APIs
#   - Artifact Registry repository
#   - Cloud Run service account + IAM bindings
#   - Secret Manager secrets (empty placeholders if missing — add values manually)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/deploy_env.sh
source "${SCRIPT_DIR}/lib/deploy_env.sh"

ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env.production}"

usage() {
  cat <<'EOF'
Usage: ./scripts/setup_cloud_run_once.sh [options]

One-time GCP infrastructure setup. Safe to re-run — skips resources that exist.

Options:
  --env-file PATH   Alternate env file (default: .env.production)
  -h, --help        Show this help

After this script:
  1. Add secret values to Secret Manager (see docs/production_setup_guide.md)
  2. Fill BUYER/VENDOR reasoning engines in .env.production (or deploy Agent Engine)
  3. Run ./scripts/deploy_cloud_run.sh

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (use --help)"
      ;;
  esac
done

require_cmd gcloud

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "${REPO_ROOT}/.env.production.example" ]]; then
    cp "${REPO_ROOT}/.env.production.example" "$ENV_FILE"
    log "Created ${ENV_FILE} from .env.production.example — edit it, then re-run."
    exit 0
  fi
  die "Missing ${ENV_FILE} and .env.production.example"
fi

load_env_file "$ENV_FILE"

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID required in .env.production}"
: "${GCP_REGION:?GCP_REGION required in .env.production}"
: "${ARTIFACT_REGISTRY_REPO:?ARTIFACT_REGISTRY_REPO required}"
: "${SERVICE_ACCOUNT:?SERVICE_ACCOUNT required}"

SA_NAME="${SERVICE_ACCOUNT%%@*}"
SA_NAME="${SA_NAME##*/}"

log "Using project=${GCP_PROJECT_ID} region=${GCP_REGION}"

log "Setting gcloud project"
gcloud config set project "$GCP_PROJECT_ID" >/dev/null

log "Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$GCP_PROJECT_ID"

if gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" \
  --location="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  log "Artifact Registry repo already exists: ${ARTIFACT_REGISTRY_REPO}"
else
  log "Creating Artifact Registry repo: ${ARTIFACT_REGISTRY_REPO}"
  gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPO" \
    --repository-format=docker \
    --location="$GCP_REGION" \
    --project="$GCP_PROJECT_ID"
fi

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  log "Service account already exists: ${SERVICE_ACCOUNT}"
else
  log "Creating service account: ${SA_NAME}"
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="ProcuForge Cloud Run runtime" \
    --project="$GCP_PROJECT_ID"
fi

bind_role() {
  local role="$1"
  log "Binding ${role} -> ${SERVICE_ACCOUNT}"
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
}

bind_role "roles/aiplatform.user"
bind_role "roles/datastore.user"

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

cat <<EOF

One-time setup finished.

Next steps:
  1. Set JWT_SECRET and ADMIN_PASSWORD_HASH in .env.production:
       uv run python scripts/generate_auth_secrets.py

  2. Deploy Agent Engine (if not done):
       uv run python -m deployment.deploy_buyer
       uv run python -m deployment.deploy_vendor

  3. Edit .env.production:
       - API_CORS_ORIGINS (your Vercel URL)
       - WORKFLOW_DEFAULT_* / ADMIN_* ids
       - Or set SYNC_REASONING_ENGINES_FROM_LOGS=true

  4. Deploy:
       ./scripts/deploy_cloud_run.sh

EOF
