# Deploy cheer API + web to Cloud Run

The **Next.js app** (`cheer-scores-web`) is what looks like **localhost:3001**.

Deploy **API first**, then **web**, so you can bake the API URL into the Next bundle.

Replace project / region / repo names if yours differ (examples use `meet-tracker-490603`, `us-central1`, Artifact Registry repo `containers`).

## 0. One-time: Artifact Registry

```bash
gcloud config set project meet-tracker-490603
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

(Create the `containers` repository in Artifact Registry if it does not exist yet.)

## 1. Build and push API image

From the **repo root** (`meet-tracker-platform`):

```bash
gcloud builds submit services/cheer-scores-api \
  --config services/cheer-scores-api/cloudbuild.yaml
```

Or from **`services/cheer-scores-api`**:

```bash
gcloud builds submit . --config cloudbuild.yaml
```

## 2. Deploy API to Cloud Run

Reuse the same Postgres secret you use for gym if the DB is shared (example secret name `DATABASE_URL`):

```bash
gcloud run deploy cheer-scores-api \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/meet-tracker-490603/containers/cheer-scores-api:latest \
  --set-secrets DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars CHEER_SCORES_CORS_ORIGINS=https://YOUR-CHEER-WEB-SERVICE-URL.run.app \
  --allow-unauthenticated \
  --port 8080
```

After the first deploy, copy the **API URL** (e.g. `https://cheer-scores-api-xxxxx.us-central1.run.app`).

Update CORS after you know the **web** URL (step 4), or temporarily use `*` only for debugging (not recommended for production):

```bash
gcloud run services update cheer-scores-api --region us-central1 \
  --set-env-vars "CHEER_SCORES_CORS_ORIGINS=https://cheer-scores-web-xxxxx.us-central1.run.app"
```

(Comma-separate multiple origins if you add a custom domain.)

## 3. Build and push **web** image (bakes `NEXT_PUBLIC_API_URL`)

Pass your **real** API URL from step 2 (no trailing slash).

From **repo root**:

```bash
gcloud builds submit services/cheer-scores-web \
  --config services/cheer-scores-web/cloudbuild.yaml \
  --substitutions=_NEXT_PUBLIC_API_URL=https://cheer-scores-api-xxxxx.us-central1.run.app
```

From **`services/cheer-scores-web`** (same build):

```bash
gcloud builds submit . --config cloudbuild.yaml \
  --substitutions=_NEXT_PUBLIC_API_URL=https://cheer-scores-api-xxxxx.us-central1.run.app
```

Or edit `substitutions` in `services/cheer-scores-web/cloudbuild.yaml` and run without `--substitutions`.

## 4. Deploy web to Cloud Run

```bash
gcloud run deploy cheer-scores-web \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/meet-tracker-490603/containers/cheer-scores-web:latest \
  --allow-unauthenticated \
  --port 8080
```

The command prints the **web** URL (e.g. `https://cheer-scores-web-xxxxx.us-central1.run.app`). Use that in step 5 for CORS on the API.

Open the **web** service URL in the browser; it should match your local MVP (search, meet pages) against cloud data.

## 5. Point API CORS at the final web URL

If the web URL changed or you map a custom domain, update `CHEER_SCORES_CORS_ORIGINS` on `cheer-scores-api` again (see step 2).

## Notes

- **No secrets** are required on the **web** container for the MVP if the API URL is only in `NEXT_PUBLIC_*` at **build** time (already in the image from step 3).
- **Database:** same `DATABASE_URL` as gym is fine; cheer uses `cheer_mvp_*` tables.
- **Redeploy web** whenever the public API URL changes (Next inlines `NEXT_PUBLIC_API_URL` at build).
