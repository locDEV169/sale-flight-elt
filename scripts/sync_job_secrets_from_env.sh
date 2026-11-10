#!/usr/bin/env bash
# Sync SERPAPI / Telegram (+ HORIZON_DAYS) from local .env → Secret Manager
# and re-bind them on Cloud Run Job sale-flight-elt.
#
# Does NOT print secret values. Requires: gcloud auth, Secret Manager API,
# roles to create/add secret versions + update the Job.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-southeast1}"
JOB_NAME="${JOB_NAME:-sale-flight-elt}"
SA_RUN="${SA_RUN:-sale-flight-runner@${PROJECT_ID}.iam.gserviceaccount.com}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

# Parse .env without `source <(...)` (flaky with spaces in path / bash 3.2).
# Supports KEY=VALUE; strips CR; skips blank/comment lines. Values may contain ':'.
load_dotenv() {
  local file="$1" line key val
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    case "${line}" in
      ""|\#*) continue ;;
    esac
    case "${line}" in
      *[=]*) ;;
      *) continue ;;
    esac
    key="${line%%=*}"
    val="${line#*=}"
    case "${key}" in
      ''|*[!A-Za-z0-9_]*|[0-9]*) continue ;;
    esac
    # Strip one layer of matching quotes if present.
    if [[ "${val}" == \"*\" ]]; then
      val="${val#\"}"
      val="${val%\"}"
    elif [[ "${val}" == \'*\' ]]; then
      val="${val#\'}"
      val="${val%\'}"
    fi
    printf -v "${key}" '%s' "${val}"
    export "${key}"
  done < "${file}"
}

load_dotenv "${ENV_FILE}"
echo "loaded env from ${ENV_FILE}"

if [[ -z "${SERPAPI_API_KEY:-}" ]]; then
  echo "ERROR: SERPAPI_API_KEY missing/empty in ${ENV_FILE}" >&2
  exit 1
fi
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN missing/empty in ${ENV_FILE}" >&2
  exit 1
fi
if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "ERROR: TELEGRAM_CHAT_ID missing/empty in ${ENV_FILE}" >&2
  exit 1
fi
HORIZON_DAYS="${HORIZON_DAYS:-1}"

if [[ "${SERPAPI_API_KEY}" == "YOUR_SERPAPI_KEY" || "${SERPAPI_API_KEY}" == "your_serpapi_api_key" ]]; then
  echo "ERROR: SERPAPI_API_KEY in .env still looks like a placeholder" >&2
  exit 1
fi

upsert_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "${name}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${name}" \
      --data-file=- --project="${PROJECT_ID}" >/dev/null
    echo "updated secret ${name} (new version)"
  else
    printf '%s' "${value}" | gcloud secrets create "${name}" \
      --data-file=- --replication-policy=automatic --project="${PROJECT_ID}" >/dev/null
    echo "created secret ${name}"
  fi
}

echo "project=${PROJECT_ID} job=${JOB_NAME} region=${REGION}"
upsert_secret SERPAPI_API_KEY "${SERPAPI_API_KEY}"
upsert_secret TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN}"
upsert_secret TELEGRAM_CHAT_ID "${TELEGRAM_CHAT_ID}"

# Ensure Job SA can read secrets (idempotent if already bound)
gcloud secrets add-iam-policy-binding SERPAPI_API_KEY \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null || true
gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null || true
gcloud secrets add-iam-policy-binding TELEGRAM_CHAT_ID \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null || true

SECRETS="SERPAPI_API_KEY=SERPAPI_API_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest"

if ! gcloud run jobs describe "${JOB_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "ERROR: Job ${JOB_NAME} not found. Run ./scripts/deploy_cloud_run.sh first." >&2
  exit 1
fi

# Re-bind secrets + refresh HORIZON_DAYS (plain env). Other GCP_* left as-is via update-*.
gcloud run jobs update "${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --update-env-vars="HORIZON_DAYS=${HORIZON_DAYS}" \
  --update-secrets="${SECRETS}"

echo "OK: secrets synced + Job ${JOB_NAME} rebound to :latest"
echo "Execute: gcloud run jobs execute ${JOB_NAME} --region=${REGION} --project=${PROJECT_ID} --wait"
