# Gym Scores Web (09)

Next.js frontend for live gymnastics meet scores. **Calls the FastAPI backend** (project 08 or a deployed API); does not talk to the database directly.

## Setup

1. **Install dependencies**

   ```bash
   cd projects/09_gym_scores_web
   npm install
   ```

2. **Configure env**

   Copy `.env.local.example` to `.env.local` and set:

   - `NEXT_PUBLIC_API_URL` – base URL of the FastAPI backend (e.g. `http://localhost:8002` for local dev).

3. **Run FastAPI backend**

   From project 08 (or wherever the API is):

   ```bash
   cd projects/08_gym_scores
   source .venv/bin/activate
   uvicorn app.main:app --reload --port 8002
   ```

   Ensure it has access to the same Supabase/DB as the ingest.

4. **Run Next.js**

   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000).

## Features (scaffold)

- **Live scores** – list of athletes with VT/UB/BB/FX/AA scores for the selected meet.
- **Filters** – level, division, search (athlete/gym).
- **Event switch** – sort and highlight by VT, UB, BB, FX, or AA.
- **Auto-refresh** – optional polling every 20s (toggle in UI).

## Architecture

- **Next.js** (this app) → HTTP → **FastAPI** (08 `app/main.py`) → **Postgres/Supabase**.
- For production: deploy FastAPI as a Cloud Run **Service** and set `NEXT_PUBLIC_API_URL` to that URL. Deploy this app to Cloud Run (or Vercel) as a separate service.
