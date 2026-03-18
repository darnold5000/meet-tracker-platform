## Cloud Run Job (ingest) setup

This project can run as a **Cloud Run Job** that scrapes MSO and writes into your Supabase Postgres DB.

### Required env vars

- `DATABASE_URL`: Supabase Postgres connection string
- `MSO_TZ`: e.g. `America/New_York`
- `MSO_ONLY_TODAY_SESSIONS`: `1` (recommended)
- `MSO_API_ENABLED`: `0` (recommended)

### Suggested secrets (Secret Manager)

- `DATABASE_URL`
- (optional) `MSO_USERNAME`, `MSO_PASSWORD` (if you add authenticated scraping later)

### Build & deploy (example commands)

Replace:
- `PROJECT_ID`
- `REGION` (e.g. `us-central1`)
- `REPO` (Artifact Registry repo name, e.g. `containers`)
- `IMAGE` (e.g. `usag-ingest`)

```bash
gcloud config set project PROJECT_ID

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories create REPO \
  --repository-format=docker \
  --location=REGION

gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest \
  .

gcloud secrets create DATABASE_URL --replication-policy="automatic"
gcloud secrets versions add DATABASE_URL --data-file=-

gcloud run jobs create usag-ingest \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars=MSO_TZ=America/New_York,MSO_ONLY_TODAY_SESSIONS=1,MSO_API_ENABLED=0 \
  --command=python \
  --args=ingest.py,--scrape-limit,1,--use-target-meets

# Run once to validate
gcloud run jobs execute usag-ingest --region=REGION

# Scheduler every minute (runs the job)
gcloud scheduler jobs create http usag-ingest-every-minute \
  --location=REGION \
  --schedule="* * * * *" \
  --uri="https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/usag-ingest:run" \
  --http-method=POST \
  --oauth-service-account-email="YOUR_SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com"
```

Notes:
- The Scheduler-to-Run call requires IAM; easiest path is creating a dedicated service account and granting it `roles/run.invoker` on the job.
- For production, consider setting Job task timeout and retries.

