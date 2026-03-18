# USAG Meet Score Tracker — Quick Start

## Prerequisites
- Python 3.10+
- PostgreSQL running locally (or connection string to a hosted DB)
- Playwright browsers installed after pip install

## Setup

```bash
cd "/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker"

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```ini
DATABASE_URL=postgresql://user:password@localhost:5432/usag_meets
```

## Create the database tables

```bash
python -c "from db.database import create_tables; create_tables()"
```

## Start the API server

```bash
uvicorn api.server:app --reload --port 8002
```

API docs available at: http://localhost:8002/docs

## Start the scheduler (in a separate terminal)

```bash
source .venv/bin/activate
python -c "
from scheduler.jobs import start_scheduler
import time
sched = start_scheduler()
print('Scheduler running. Press Ctrl+C to stop.')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    sched.shutdown()
"
```

## Run a manual meet discovery

```bash
python -c "
from agents.meet_discovery import discover_meets
meets = discover_meets()
for m in meets[:5]:
    print(m)
"
```

## Run tests

```bash
pytest tests/ -v
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /meets` | List all meets |
| `GET /meets/{id}` | Single meet |
| `GET /meets/{id}/scores` | All scores for a meet |
| `GET /athletes` | List athletes |
| `GET /athletes/{id}` | Athlete profile |
| `GET /athletes/{id}/history` | Full meet history |
| `GET /scores` | Recent scores (filterable) |
| `GET /gyms` | All gyms |
| `GET /gyms/{id}` | Gym + athletes |

## Job Schedule

| Job | When |
|-----|------|
| Meet discovery | Daily 6am ET |
| MSO scrape | Every 60 minutes |
| Website crawl | Every 6 hours |
| ScoreCat live poll | Every 10s (active meets only, trigger manually) |

## ScoreCat Live Polling

To start live polling for a specific meet:

```bash
python -c "
from agents.scorecat_agent import run_live_polling
import threading
stop = threading.Event()
for record in run_live_polling('YOUR_SCORECAT_MEET_ID', stop_event=stop):
    print(record)
"
```

> Note: ScoreCat meetId comes from the meet URL. Look for the numeric ID in the URL path.
