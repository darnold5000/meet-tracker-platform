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

## Deploy

1. Set `_NEXT_PUBLIC_API_URL` in `cloudbuild.yaml` to your deployed **cheer** API URL.
2. `gcloud builds submit services/cheer-scores-web --config services/cheer-scores-web/cloudbuild.yaml`
3. Map your cheer domain to the new Cloud Run service and add that origin to the API’s `CHEER_SCORES_CORS_ORIGINS`.
