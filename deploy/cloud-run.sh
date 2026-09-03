#!/usr/bin/env bash
# This script was created entirely by Codex to deploy this project to Cloud Run.
# It will be maintained by Codex going forward.

set -euo pipefail

CONFIG_FILE="${1:-deploy/cloud-run.env}"
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing deployment config: $CONFIG_FILE" >&2
  echo "Copy deploy/cloud-run.env.example and fill in its values." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

required_variables=(
  PROJECT_ID REGION ARTIFACT_REPOSITORY
  TRACKER_SERVICE UPDATER_JOB SCHEDULER_JOB SCHEDULE TIME_ZONE
  INC_EXP_DATABASE_ID CATEGORIES_DATABASE_ID ACCOUNTS_DATABASE_ID
  ASSETS_DATABASE_ID HOLDINGS_DATABASE_ID CURRENCIES_DATABASE_ID
  PLATFORMS_DATABASE_ID PROPERTIES_DATABASE_ID NET_VALUE_DATABASE_ID
  AI_SNAPSHOT_PAGE_ID
  MODEL_BASE_URL MODEL_NAME CACHE_TTL_SECONDS
)

for variable in "${required_variables[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    echo "Missing $variable in $CONFIG_FILE" >&2
    exit 1
  fi
done

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  cloudscheduler.googleapis.com

secrets=(INTERNAL_INTEGRATION_TOKEN MODEL_API_KEY TRACKER_API_TOKEN)
for secret in "${secrets[@]}"; do
  if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "Missing Secret Manager secret: $secret" >&2
    exit 1
  fi
done

if ! gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" \
  --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --location "$REGION" \
    --repository-format docker
fi

image_tag="$(date -u +%Y%m%d-%H%M%S)"
registry="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}"
tracker_image="${registry}/tracker:${image_tag}"
updater_image="${registry}/updater:${image_tag}"

gcloud builds submit --tag "$tracker_image" .
gcloud builds submit \
  --config cloudbuild.updater.yaml \
  --substitutions "_IMAGE=${updater_image}" \
  .

tracker_sa="notion-tracker-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
updater_sa="notion-updater-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
scheduler_sa="notion-updater-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

ensure_service_account() {
  local account_name="$1"
  local display_name="$2"
  if ! gcloud iam service-accounts describe \
    "${account_name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$account_name" \
      --display-name "$display_name"
  fi
}

ensure_service_account notion-tracker-runtime "Notion Tracker Runtime"
ensure_service_account notion-updater-runtime "Notion Updater Runtime"
ensure_service_account notion-updater-scheduler "Notion Updater Scheduler"

grant_secret_access() {
  local secret="$1"
  local service_account="$2"
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${service_account}" \
    --role roles/secretmanager.secretAccessor \
    --quiet >/dev/null
}

grant_secret_access INTERNAL_INTEGRATION_TOKEN "$tracker_sa"
grant_secret_access MODEL_API_KEY "$tracker_sa"
grant_secret_access TRACKER_API_TOKEN "$tracker_sa"
grant_secret_access INTERNAL_INTEGRATION_TOKEN "$updater_sa"

gcloud run deploy "$TRACKER_SERVICE" \
  --image "$tracker_image" \
  --region "$REGION" \
  --service-account "$tracker_sa" \
  --allow-unauthenticated \
  --concurrency 4 \
  --max-instances 2 \
  --timeout 60 \
  --set-env-vars "INC_EXP_DATABASE_ID=${INC_EXP_DATABASE_ID},CATEGORIES_DATABASE_ID=${CATEGORIES_DATABASE_ID},ACCOUNTS_DATABASE_ID=${ACCOUNTS_DATABASE_ID},MODEL_BASE_URL=${MODEL_BASE_URL},MODEL_NAME=${MODEL_NAME},CACHE_TTL_SECONDS=${CACHE_TTL_SECONDS}" \
  --set-secrets "INTERNAL_INTEGRATION_TOKEN=INTERNAL_INTEGRATION_TOKEN:latest,MODEL_API_KEY=MODEL_API_KEY:latest,TRACKER_API_TOKEN=TRACKER_API_TOKEN:latest" \
  --quiet

gcloud run jobs deploy "$UPDATER_JOB" \
  --image "$updater_image" \
  --region "$REGION" \
  --service-account "$updater_sa" \
  --command "" \
  --args "" \
  --tasks 1 \
  --max-retries 1 \
  --task-timeout 20m \
  --set-env-vars "ASSETS_DATABASE_ID=${ASSETS_DATABASE_ID},HOLDINGS_DATABASE_ID=${HOLDINGS_DATABASE_ID},CURRENCIES_DATABASE_ID=${CURRENCIES_DATABASE_ID},PLATFORMS_DATABASE_ID=${PLATFORMS_DATABASE_ID},ACCOUNTS_DATABASE_ID=${ACCOUNTS_DATABASE_ID},PROPERTIES_DATABASE_ID=${PROPERTIES_DATABASE_ID},NET_VALUE_DATABASE_ID=${NET_VALUE_DATABASE_ID},AI_SNAPSHOT_PAGE_ID=${AI_SNAPSHOT_PAGE_ID}" \
  --set-secrets "INTERNAL_INTEGRATION_TOKEN=INTERNAL_INTEGRATION_TOKEN:latest" \
  --quiet

gcloud run jobs add-iam-policy-binding "$UPDATER_JOB" \
  --region "$REGION" \
  --member "serviceAccount:${scheduler_sa}" \
  --role roles/run.invoker \
  --quiet >/dev/null

scheduler_uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${UPDATER_JOB}:run"
scheduler_args=(
  --location "$REGION"
  --schedule "$SCHEDULE"
  --time-zone "$TIME_ZONE"
  --attempt-deadline 180s
  --uri "$scheduler_uri"
  --http-method POST
  --oauth-service-account-email "$scheduler_sa"
  --oauth-token-scope https://www.googleapis.com/auth/cloud-platform
  --quiet
)

if gcloud scheduler jobs describe "$SCHEDULER_JOB" \
  --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB" "${scheduler_args[@]}"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB" "${scheduler_args[@]}"
fi

tracker_url=$(gcloud run services describe "$TRACKER_SERVICE" \
  --region "$REGION" \
  --format 'value(status.url)')

echo "Tracker: $tracker_url"
echo "Updater: $UPDATER_JOB"
echo "Scheduler: $SCHEDULER_JOB ($SCHEDULE, $TIME_ZONE)"
