#!/usr/bin/env bash
# Shared helpers for Cloud Run deploy scripts.
# shellcheck disable=SC2034

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Cloud Run container env var names (order preserved for stable diffs).
CLOUD_RUN_RUNTIME_ENV_KEYS=(
  API_ENV
  GOOGLE_CLOUD_PROJECT
  GOOGLE_CLOUD_LOCATION
  GOOGLE_GENAI_USE_VERTEXAI
  BUYER_REASONING_ENGINE
  VENDOR_REASONING_ENGINE
  VENDOR_A2A_AGENT_CARD_URL
  VENDOR_SERVER_HOST
  VENDOR_SERVER_PORT
  WORKFLOW_DEFAULT_USER_ID
  WORKFLOW_DEFAULT_ORGANIZATION_ID
  API_CORS_ORIGINS
  JWT_SECRET
  ADMIN_PASSWORD_HASH
  ADMIN_USER_ID
  ADMIN_ORG_ID
  ADMIN_USER_NAME
  ADMIN_USER_EMAIL
  ADMIN_USER_ROLE
  ADMIN_ORG_NAME
  ADMIN_ORG_CURRENCY
)

# Auth vars that may have been bound via Secret Manager on older deploys.
CLOUD_RUN_AUTH_ENV_KEYS=(
  JWT_SECRET
  ADMIN_PASSWORD_HASH
)

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: ${cmd}"
  done
}

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || die "Env file not found: ${file}\nCopy .env.production.example to .env.production and fill in values."

  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
}

validate_auth_config() {
  if [[ -z "${JWT_SECRET:-}" ]]; then
    die "JWT_SECRET required in .env.production (run: uv run python scripts/generate_auth_secrets.py)"
  fi
  if [[ -z "${ADMIN_PASSWORD_HASH:-}" ]]; then
    die "ADMIN_PASSWORD_HASH required in .env.production"
  fi
}

validate_deploy_config() {
  local missing=()
  local key

  validate_auth_config

  for key in \
    GCP_PROJECT_ID \
    GCP_REGION \
    CLOUD_RUN_SERVICE \
    ARTIFACT_REGISTRY_REPO \
    IMAGE_NAME \
    SERVICE_ACCOUNT; do
    if [[ -z "${!key:-}" ]]; then
      missing+=("$key")
    fi
  done

  for key in \
    API_ENV \
    GOOGLE_CLOUD_PROJECT \
    GOOGLE_CLOUD_LOCATION \
    GOOGLE_GENAI_USE_VERTEXAI \
    BUYER_REASONING_ENGINE \
    VENDOR_REASONING_ENGINE \
    VENDOR_A2A_AGENT_CARD_URL \
    VENDOR_SERVER_HOST \
    VENDOR_SERVER_PORT \
    WORKFLOW_DEFAULT_USER_ID \
    WORKFLOW_DEFAULT_ORGANIZATION_ID \
    API_CORS_ORIGINS; do
    if [[ -z "${!key:-}" ]]; then
      missing+=("$key")
    fi
  done

  if ((${#missing[@]} > 0)); then
    die "Missing required variables in .env.production: ${missing[*]}"
  fi

  if [[ "${API_CORS_ORIGINS}" == *"your-app.vercel.app"* ]]; then
    die "Set API_CORS_ORIGINS to your real Vercel URL in .env.production"
  fi

  if [[ "${BUYER_REASONING_ENGINE}" == *"PROJECT_NUMBER"* ]] \
    || [[ "${VENDOR_REASONING_ENGINE}" == *"PROJECT_NUMBER"* ]]; then
    die "Set BUYER_REASONING_ENGINE and VENDOR_REASONING_ENGINE in .env.production (or enable SYNC_REASONING_ENGINES_FROM_LOGS=true)"
  fi
}

sync_reasoning_engines_from_logs() {
  local buyer_meta="${REPO_ROOT}/logs/procu-forge-buyer_deployment_metadata.json"
  local vendor_meta="${REPO_ROOT}/logs/procu-forge-vendor_deployment_metadata.json"

  if [[ -f "$buyer_meta" ]]; then
    BUYER_REASONING_ENGINE="$(
      python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['remote_agent_engine_id'])" "$buyer_meta"
    )"
    log "BUYER_REASONING_ENGINE from ${buyer_meta}"
  fi

  if [[ -f "$vendor_meta" ]]; then
    VENDOR_REASONING_ENGINE="$(
      python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['remote_agent_engine_id'])" "$vendor_meta"
    )"
    log "VENDOR_REASONING_ENGINE from ${vendor_meta}"
  fi
}

image_uri() {
  local tag="${IMAGE_TAG:-latest}"
  printf '%s-docker.pkg.dev/%s/%s/%s:%s' \
    "$GCP_REGION" "$GCP_PROJECT_ID" "$ARTIFACT_REGISTRY_REPO" "$IMAGE_NAME" "$tag"
}

# Comma-separated auth env names still bound as Secret Manager refs (empty if none).
cloud_run_bound_auth_secret_keys() {
  local raw=""

  if ! raw="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --project="$GCP_PROJECT_ID" \
    --region="$GCP_REGION" \
    --format='json(spec.template.spec.containers[0].env)' 2>/dev/null)"; then
    return 0
  fi

  printf '%s' "$raw" | python3 -c '
import json
import sys


def env_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        try:
            return data["spec"]["template"]["spec"]["containers"][0]["env"] or []
        except (KeyError, IndexError, TypeError):
            return []
    return []


raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)

targets = {"JWT_SECRET", "ADMIN_PASSWORD_HASH"}
bound = [
    item["name"]
    for item in env_list(json.loads(raw))
    if isinstance(item, dict)
    and item.get("name") in targets
    and item.get("valueFrom", {}).get("secretKeyRef")
]
print(",".join(bound))
'
}

# gcloud run deploy cannot switch secret refs to plain literals in one step.
# services update with the full env-vars file removes bindings and sets literals together.
migrate_cloud_run_auth_secrets_to_env() {
  local bound="$1"
  local env_file="$2"

  [[ -n "$bound" ]] || return 0
  [[ -f "$env_file" ]] || die "Env vars file not found for secret migration: ${env_file}"

  log "Migrating auth env from Secret Manager to plain values: ${bound}"
  gcloud run services update "$CLOUD_RUN_SERVICE" \
    --project="$GCP_PROJECT_ID" \
    --region="$GCP_REGION" \
    --remove-secrets="$bound" \
    --env-vars-file="$env_file" \
    --quiet
}

write_cloud_run_env_file() {
  local out="$1"
  local key

  for key in "${CLOUD_RUN_RUNTIME_ENV_KEYS[@]}"; do
    if [[ -n "${!key:-}" ]]; then
      export "$key"
    fi
  done

  # gcloud --env-vars-file requires YAML or JSON (map), not dotenv KEY=value lines.
  python3 - "$out" <<'PY'
import json
import os
import sys

keys = [
    "API_ENV",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "BUYER_REASONING_ENGINE",
    "VENDOR_REASONING_ENGINE",
    "VENDOR_A2A_AGENT_CARD_URL",
    "VENDOR_SERVER_HOST",
    "VENDOR_SERVER_PORT",
    "WORKFLOW_DEFAULT_USER_ID",
    "WORKFLOW_DEFAULT_ORGANIZATION_ID",
    "API_CORS_ORIGINS",
    "JWT_SECRET",
    "ADMIN_PASSWORD_HASH",
    "ADMIN_USER_ID",
    "ADMIN_ORG_ID",
    "ADMIN_USER_NAME",
    "ADMIN_USER_EMAIL",
    "ADMIN_USER_ROLE",
    "ADMIN_ORG_NAME",
    "ADMIN_ORG_CURRENCY",
]

out_path = sys.argv[1]
data = {key: os.environ[key] for key in keys if os.environ.get(key)}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
}

verify_deployment() {
  local url
  url="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --project="$GCP_PROJECT_ID" \
    --region="$GCP_REGION" \
    --format='value(status.url)' 2>/dev/null)" || die "Could not resolve Cloud Run service URL"

  log "Service URL: ${url}"
  log "GET ${url}/health"
  curl -sf "${url}/health" >/dev/null || die "Health check failed"

  log "GET ${url}/health/ready"
  if ! curl -sf "${url}/health/ready" >/dev/null; then
    log "Readiness check failed — inspect response:"
    curl -s "${url}/health/ready" || true
    die "Readiness check failed"
  fi

  log "Health checks passed"
}
