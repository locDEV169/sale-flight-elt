#!/usr/bin/env bash
# Create or update Cloud Scheduler → trigger Cloud Run Job sale-flight-elt.
# Schedule: 08:00 and 20:00 Asia/Ho_Chi_Minh (does not rebuild the Job image).
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"

REGION="${REGION:-asia-southeast1}"
JOB_NAME="${JOB_NAME:-sale-flight-elt}"
SCHEDULER_NAME="${SCHEDULER_NAME:-sale-flight-elt-cron}"
SCHEDULE="${SCHEDULE:-0 8,20 * * *}"
TIME_ZONE="${TIME_ZONE:-Asia/Ho_Chi_Minh}"
SA_SCHEDULER="${SA_SCHEDULER:-sale-flight-scheduler@${PROJECT_ID}.iam.gserviceaccount.com}"
SA_SCHEDULER_ID="${SA_SCHEDULER_ID:-sale-flight-scheduler}"

# Cloud Run Jobs trigger URI (API v1)
URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

echo "project=${PROJECT_ID} region=${REGION}"
echo "job=${JOB_NAME} scheduler=${SCHEDULER_NAME}"
echo "schedule='${SCHEDULE}' tz=${TIME_ZONE}"

gcloud services enable \
  cloudscheduler.googleapis.com \
  run.googleapis.com \
  --project="${PROJECT_ID}" >/dev/null

if ! gcloud run jobs describe "${JOB_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "ERROR: Cloud Run Job ${JOB_NAME} not found in ${REGION}." >&2
  echo "Deploy the job first: ./scripts/deploy_cloud_run.sh" >&2
  exit 1
fi

if ! gcloud iam service-accounts describe "${SA_SCHEDULER}" \
  --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_SCHEDULER_ID}" \
    --display-name="sale-flight Scheduler" \
    --project="${PROJECT_ID}"
  echo "created SA ${SA_SCHEDULER}"
else
  echo "SA exists ${SA_SCHEDULER}"
fi

gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_SCHEDULER}" \
  --role="roles/run.invoker" >/dev/null
echo "granted roles/run.invoker on ${JOB_NAME}"

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" \
  --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --schedule="${SCHEDULE}" \
    --time-zone="${TIME_ZONE}" \
    --uri="${URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SA_SCHEDULER}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
  echo "updated scheduler ${SCHEDULER_NAME}"
else
  gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --schedule="${SCHEDULE}" \
    --time-zone="${TIME_ZONE}" \
    --uri="${URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SA_SCHEDULER}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
  echo "created scheduler ${SCHEDULER_NAME}"
fi

echo "OK: describe with:"
echo "  gcloud scheduler jobs describe ${SCHEDULER_NAME} --location=${REGION} --project=${PROJECT_ID}"
echo "Fire once:"
echo "  gcloud scheduler jobs run ${SCHEDULER_NAME} --location=${REGION} --project=${PROJECT_ID}"
