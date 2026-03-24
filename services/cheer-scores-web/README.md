# Cheer Scores Web

Next.js frontend for **cheer** competition scores. Calls the `cheer-scores-api` FastAPI service only (no direct DB access).

## Local dev

Run the API on port **8003** (see `services/cheer-scores-api/README.md`), then:

1. In `services/ingest-cheer`, with the same `DATABASE_URL` as the API:  
   `python3 -c "from db.database import create_tables; create_tables()"`  
   `python3 scripts/seed_cheer_mvp.py`  
   Demo meet keys: **`DEMO-ATL-2026`** (Atlanta), **`DEMO-CHI-2026`** (Chicago).

```bash
cd services/cheer-scores-web
cp .env.local.example .env.local
# Either: NEXT_PUBLIC_API_URL=http://127.0.0.1:8003
# Or (easiest if you see "Failed to fetch"): NEXT_PUBLIC_API_VIA_PROXY=1
npm install
npm run dev -- -p 3001
```

If the UI shows **Failed to fetch**: the browser could not reach the API (wrong URL, API stopped) or CORS blocked it. Use **`NEXT_PUBLIC_API_VIA_PROXY=1`** and restart dev — requests go to `/api-proxy/...` and Next forwards to `http://127.0.0.1:8003`. Ensure the API is running on that port.

The home page is the **MVP**: search, open a meet for **timeline** and **results**.

Using port **3001** avoids clashing with `gym-scores-web` on **3000**.

## Deploy (Cloud Run)

The UI matches **localhost:3001** once the Next image is built with the **real** cheer API URL and CORS is set on the API.

**Order:** deploy **cheer-scores-api** first, then build **cheer-scores-web** with `--substitutions=_NEXT_PUBLIC_API_URL=...`, then deploy the web service. Step-by-step: [`../cheer-scores-api/CLOUD_RUN.md`](../cheer-scores-api/CLOUD_RUN.md).

Short version:

1. Build/push API: `gcloud builds submit services/cheer-scores-api --config services/cheer-scores-api/cloudbuild.yaml`
2. `gcloud run deploy cheer-scores-api ...` with `DATABASE_URL` secret; note the service URL.
3. Build/push web with that URL:  
   `gcloud builds submit services/cheer-scores-web --config services/cheer-scores-web/cloudbuild.yaml --substitutions=_NEXT_PUBLIC_API_URL=https://YOUR-API.run.app`
4. `gcloud run deploy cheer-scores-web ...`
5. Set `CHEER_SCORES_CORS_ORIGINS` on the API to your **web** Cloud Run URL (or custom domain).
