#!/usr/bin/env bash
# Build image → create/update Cloud Run Job (Option A).
# Does NOT create IAM/secrets/scheduler — see docs/DEPLOY_CLOUD_RUN.md §§1–3,6–7.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${GCS_BUCKET:?Set GCS_BUCKET}"

REGION="${REGION:-asia-southeast1}"
REPO="${REPO:-sale-flight}"
JOB_NAME="${JOB_NAME:-sale-flight-elt}"
BQ_DATASET="${BQ_DATASET:-flight_elt}"
HORIZON_DAYS="${HORIZON_DAYS:-0}"
SA_RUN="${SA_RUN:-sale-flight-runner@${PROJECT_ID}.iam.gserviceaccount.com}"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/elt:latest}"

echo "project=${PROJECT_ID} region=${REGION} image=${IMAGE} job=${JOB_NAME}"

if ! gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
fi

gcloud builds submit --tag "${IMAGE}" --project="${PROJECT_ID}"

ENV_VARS="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET},BQ_LOCATION=${REGION},GCS_BUCKET=${GCS_BUCKET},HORIZON_DAYS=${HORIZON_DAYS}"
SECRETS="SERPAPI_API_KEY=SERPAPI_API_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest"

if gcloud run jobs describe "${JOB_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud run jobs update "${JOB_NAME}" \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="${SA_RUN}" \
    --memory=1Gi \
    --cpu=1 \
    --task-timeout=15m \
    --max-retries=0 \
    --set-env-vars="${ENV_VARS}" \
    --set-secrets="${SECRETS}"
  echo "updated job ${JOB_NAME}"
else
  gcloud run jobs create "${JOB_NAME}" \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="${SA_RUN}" \
    --memory=1Gi \
    --cpu=1 \
    --task-timeout=15m \
    --max-retries=0 \
    --set-env-vars="${ENV_VARS}" \
    --set-secrets="${SECRETS}"
  echo "created job ${JOB_NAME}"
fi

echo "OK: deploy done. Execute: gcloud run jobs execute ${JOB_NAME} --region=${REGION} --project=${PROJECT_ID} --wait"
