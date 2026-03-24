# Cheer Scores API

FastAPI backend for the **cheer** scores product. Same read patterns as `gym-scores-api` today (Postgres `meets` / `scores` / etc.); use a **separate `DATABASE_URL`** for cheer data.

## Run locally

```bash
cd services/cheer-scores-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL, optional CHEER_SCORES_* vars
uvicorn app.main:app --reload --port 8003
```

Point `services/cheer-scores-web` at `http://127.0.0.1:8003` via `NEXT_PUBLIC_API_URL`.

### Cheer MVP API (`cheer_mvp_*` tables)

After `create_tables()` and `python scripts/seed_cheer_mvp.py` in `ingest-cheer` (same `DATABASE_URL`):

- `GET /api/mvp/search?q=` — teams + meets (empty `q` returns recent lists)
- `GET /api/mvp/meet/{meet_key}/timeline?session_id=` — sessions + ordered timeline rows
- `GET /api/mvp/meet/{meet_key}/results?session_id=` — ranked scores (non-break rows with `final_score`)

## Deploy

Mirror the gym API: build the `Dockerfile`, push to Artifact Registry, create a **new** Cloud Run service (e.g. `cheer-scores-api`), set secrets/env, then set `CHEER_SCORES_CORS_ORIGINS` to your cheer web origin(s).

## Legacy / tools

- `streamlit_app.py` — optional dashboard; requires `CHEER_SCORES_MEET_KEY`.
- `scripts/scrape_mso.py` — MSO-oriented helpers carried over from the gym fork; replace with cheer-specific sources when ready.
