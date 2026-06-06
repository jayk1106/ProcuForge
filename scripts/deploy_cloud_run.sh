#!/usr/bin/env bash
# Build, push, and deploy ProcuForge API to Cloud Run.
#
# Usage:
#   ./scripts/deploy_cloud_run.sh              # full deploy
#   ./scripts/deploy_cloud_run.sh --skip-build # push + deploy only
#   ./scripts/deploy_cloud_run.sh --dry-run    # print commands, do not run
#
# Configuration: .env.production (copy from .env.production.example)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/deploy_env.sh
source "${SCRIPT_DIR}/lib/deploy_env.sh"

ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env.production}"

SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy_cloud_run.sh [options]

Builds the Docker image, pushes to Artifact Registry, and deploys to Cloud Run
using variables from .env.production.

Options:
  --env-file PATH   Alternate env file (default: .env.production)
  --skip-build      Skip docker build (reuse local tag)
  --skip-push       Skip docker push (image already in registry)
  --no-verify       Skip post-deploy health checks
  --dry-run         Print planned actions without executing
  -h, --help        Show this help

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    --skip-push)
      SKIP_PUSH=true
      shift
      ;;
    --no-verify)
      VERIFY_AFTER_DEPLOY=false
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
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

run() {
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] $*"
    return 0
  fi
  log "$*"
  "$@"
}

require_cmd gcloud docker curl python3

load_env_file "$ENV_FILE"

if [[ "${SYNC_REASONING_ENGINES_FROM_LOGS:-false}" == true ]]; then
  sync_reasoning_engines_from_logs
fi

validate_deploy_config

IMAGE="$(image_uri)"
REGISTRY_HOST="${GCP_REGION}-docker.pkg.dev"
ENV_VARS_FILE="$(mktemp "${TMPDIR:-/tmp}/procuforge-cloudrun-env.XXXXXX.json")"
trap 'rm -f "$ENV_VARS_FILE"' EXIT

write_cloud_run_env_file "$ENV_VARS_FILE"

CLOUD_RUN_PORT="${CLOUD_RUN_PORT:-8080}"
CLOUD_RUN_TIMEOUT="${CLOUD_RUN_TIMEOUT:-3600}"
CLOUD_RUN_MIN_INSTANCES="${CLOUD_RUN_MIN_INSTANCES:-1}"
CLOUD_RUN_MAX_INSTANCES="${CLOUD_RUN_MAX_INSTANCES:-3}"
CLOUD_RUN_CPU="${CLOUD_RUN_CPU:-2}"
CLOUD_RUN_MEMORY="${CLOUD_RUN_MEMORY:-2Gi}"
VERIFY_AFTER_DEPLOY="${VERIFY_AFTER_DEPLOY:-true}"

ALLOW_FLAG=()
if [[ "${CLOUD_RUN_ALLOW_UNAUTHENTICATED:-true}" == true ]]; then
  ALLOW_FLAG=(--allow-unauthenticated)
fi

SESSION_FLAG=()
if [[ "${CLOUD_RUN_SESSION_AFFINITY:-true}" == true ]]; then
  SESSION_FLAG=(--session-affinity)
fi

log "Project=${GCP_PROJECT_ID} Region=${GCP_REGION} Service=${CLOUD_RUN_SERVICE}"
log "Image=${IMAGE}"

if [[ "$SKIP_BUILD" != true ]]; then
  # Cloud Run is linux/amd64; Mac Docker Desktop defaults to arm64 without this.
  DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
  run docker build --platform "$DOCKER_PLATFORM" -t "$IMAGE" "$REPO_ROOT"
fi

if [[ "$SKIP_PUSH" != true ]]; then
  run gcloud auth configure-docker "${REGISTRY_HOST}" --quiet
  run docker push "$IMAGE"
fi

BOUND_AUTH_SECRETS="$(cloud_run_bound_auth_secret_keys)"
if [[ -n "$BOUND_AUTH_SECRETS" ]]; then
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] gcloud run services update ${CLOUD_RUN_SERVICE} --remove-secrets=${BOUND_AUTH_SECRETS} --env-vars-file=${ENV_VARS_FILE}"
  else
    migrate_cloud_run_auth_secrets_to_env "$BOUND_AUTH_SECRETS" "$ENV_VARS_FILE"
  fi
fi

DEPLOY_ARGS=(
  gcloud run deploy "$CLOUD_RUN_SERVICE"
  --project="$GCP_PROJECT_ID"
  --region="$GCP_REGION"
  --image="$IMAGE"
  --service-account="$SERVICE_ACCOUNT"
  --port="$CLOUD_RUN_PORT"
  --timeout="$CLOUD_RUN_TIMEOUT"
  --min-instances="$CLOUD_RUN_MIN_INSTANCES"
  --max-instances="$CLOUD_RUN_MAX_INSTANCES"
  --cpu="$CLOUD_RUN_CPU"
  --memory="$CLOUD_RUN_MEMORY"
  --env-vars-file="$ENV_VARS_FILE"
  --quiet
)

DEPLOY_ARGS+=("${ALLOW_FLAG[@]}")
DEPLOY_ARGS+=("${SESSION_FLAG[@]}")

run "${DEPLOY_ARGS[@]}"

if [[ "$VERIFY_AFTER_DEPLOY" == true && "$DRY_RUN" != true ]]; then
  verify_deployment
fi

log "Deploy complete."
