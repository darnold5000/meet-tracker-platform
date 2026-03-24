# Cheer competition ingest

Fork of `services/ingest-meets` for **cheer** data. Pipelines, agents, and docs still reflect the original gymnastics/MSO workflow until you add cheer-specific sources. Use a **separate `DATABASE_URL`** from the gym ingest job.

**Use Python 3** (`python3`, not `python`). On many Macs, `python` is still Python 2 and will fail on type hints and modern syntax.

---

# USAG Gymnastics Meet Tracker (original)

A backend service that automatically discovers USAG gymnastics meets, pulls live scores, scrapes final results, normalizes data, and exposes a unified API.

## What It Does

- **Meet Discovery** — daily job finds upcoming meets from USAG calendars and MeetScoresOnline
- **Live Scoring** — polls ScoreCat JSON feeds every 10 seconds during active meets
- **Result Scraping** — scrapes MeetScoresOnline result pages for finalized scores
- **PDF/HTML Parsing** — downloads and parses score sheets from individual meet websites
- **Data Normalization** — converts all sources into a single unified schema
- **Athlete Identity Resolution** — fuzzy name matching links the same athlete across meets with different name formats
- **Deduplication** — hash-based update detection prevents duplicate records
- **Public API** — FastAPI endpoints for meets, athletes, scores, and gyms
- **Scheduling** — APScheduler runs all jobs automatically

## Architecture

```
Meet Discovery Agent
        │
        ▼
Source Detection
        │
 ┌──────────────────────────────────────────┐
 ▼               ▼                ▼
ScoreCat Agent   MSO Scraper      Website Parser
(live scores)    (results pages)  (PDF/HTML/CSV)
 └──────────────────────────────────────────┘
                │
        Data Normalization
                │
        Athlete Matching
                │
           PostgreSQL
                │
           FastAPI
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for setup steps.

## Tech Stack

| Layer | Tool |
|-------|------|
| Scraping | Playwright + requests |
| HTML parsing | BeautifulSoup4 |
| PDF extraction | pdfplumber + pytesseract |
| Athlete matching | rapidfuzz |
| Database | PostgreSQL + SQLAlchemy |
| Migrations | Alembic |
| API | FastAPI |
| Scheduling | APScheduler |

## Project Structure

```
06_usag_meet_tracker/
├── agents/
│   ├── meet_discovery.py       # Find upcoming meets
│   ├── source_detector.py      # Detect result source type
│   ├── scorecat_agent.py       # ScoreCat live polling
│   ├── mso_scraper.py          # MeetScoresOnline scraper
│   └── website_parser.py       # PDF/HTML/CSV parser
├── core/
│   ├── normalizer.py           # Unified data normalization
│   ├── athlete_resolver.py     # Fuzzy identity matching
│   └── hasher.py               # Dedup via hashing
├── db/
│   ├── models.py               # SQLAlchemy ORM models
│   └── database.py             # Session factory
├── api/
│   ├── server.py               # FastAPI app
│   └── routes/                 # meets, athletes, scores, gyms
└── scheduler/
    └── jobs.py                 # APScheduler job definitions
```

## Job Schedule

| Job | Frequency |
|-----|-----------|
| Meet discovery | Daily 6am |
| ScoreCat polling | Every 10s (active meets only) |
| MSO scrape | Every hour |
| Website crawl | Every 6 hours |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/meets` | List all meets |
| GET | `/meets/{id}/scores` | Scores for a meet |
| GET | `/athletes/{id}` | Athlete profile |
| GET | `/athletes/{id}/history` | Full meet history |
| GET | `/gyms/{id}` | Gym profile |

## Key Engineering Notes

**Athlete identity** is the hardest problem. The same athlete appears as `Jane Smith`, `Smith, Jane`, and `Jane A. Smith` across meets. This service uses `rapidfuzz` fuzzy matching combined with gym and level cross-referencing to build a canonical athlete identity graph.

**Deduplication** — live feeds resend unchanged scores constantly. Each record is hashed on ingest and skipped if already stored.

**ScoreCat endpoints** are reverse-engineered from network inspection. The base pattern is `https://scorecat.com/api/liveScores?meetId={id}`.

---

## Current State

The backend pipeline is fully scaffolded but **no data has been persisted yet** — there is no `.db` file or CSV output. The scraper (`mso_scraper.py`) was run previously but was stopped before completion or data wasn't flushed to disk.

**What's built:**
- ✅ All scraping agents (`mso_scraper`, `meet_discovery`, `scorecat_agent`, `website_parser`, `source_detector`)
- ✅ Core processing (`normalizer`, `athlete_resolver`, `hasher`)
- ✅ Database models (SQLAlchemy ORM for meets, athletes, scores, gyms)
- ✅ FastAPI server + all route handlers
- ✅ APScheduler job definitions
- ✅ `ingest.py` orchestration entry point
- ✅ Unit tests for hasher, resolver, normalizer

**What's missing:**
- ❌ No data saved yet (no `.db` file, no CSVs)
- ❌ No Streamlit dashboard (frontend not started)
- ❌ Not deployed

---

## TODO / Next Steps

### Step 1 — Get data flowing
- [ ] **Run `ingest.py`** and confirm data saves to the SQLite DB.
  The DB path is configured in `db/database.py` — verify it exists after a run.
- [ ] **Debug any scraper issues** — `mso_scraper.py` uses Playwright. If it times out or
  hits anti-bot blocks, check the fallback logic and add retry handling.
- [ ] **Verify at least one full meet's worth of data** is in the DB (athletes, scores, meet record).

### Step 2 — Build the dashboard
- [ ] **Create `dashboard/app.py`** using Streamlit — read from the SQLite DB directly.
- [ ] **Key views to build:**
  - Meet results browser (select meet → see full score sheet)
  - Athlete profile page (career history, score trends by event)
  - Rankings by level and event (AA, VT, UB, BB, FX)
  - Score trend charts over time per athlete
- [ ] **Deploy to Streamlit Community Cloud** (GitHub repo: `darnold5000/USAG_meet_tracker`)

### Step 3 — Polish
- [ ] Add live score polling UI (show in-progress meet scores refreshing)
- [ ] Athlete search / autocomplete
- [ ] Filter by gym, level, season

eventually want a duplicate detection query that catches things like:

Sophie Arnold
Sophie M Arnold
Sophia Arnold
Sophie Arn0ld

Those won't violate the unique index but are probably the same athlete.

Postgres has a fuzzy matching extension (pg_trgm) that works extremely well for this.
