"""
ScoreCat Live Polling Agent

Polls ScoreCat JSON endpoints for near-real-time scores during active meets.
Polls every SCORECAT_POLL_INTERVAL_SECONDS (default 10s).
Stores only changed/new records using hash-based deduplication.
"""

import os
import time
import logging
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("SCORECAT_POLL_INTERVAL_SECONDS", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

# Reverse-engineered ScoreCat endpoint patterns
SCORECAT_BASE = "https://www.scorecat.com"
LIVE_SCORES_ENDPOINT = f"{SCORECAT_BASE}/api/liveScores"
RESULTS_ENDPOINT = f"{SCORECAT_BASE}/api/results"


def poll_scorecat(meet_id: str) -> Optional[List[Dict]]:
    """
    Fetch current scores from ScoreCat for a given meetId.
    Returns a list of raw score dicts, or None on failure.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; USAGTracker/1.0)",
        "Accept": "application/json",
    }

    # Try live scores endpoint first
    for endpoint in [LIVE_SCORES_ENDPOINT, RESULTS_ENDPOINT]:
        try:
            resp = requests.get(
                endpoint,
                params={"meetId": meet_id},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.debug("ScoreCat %s returned %d records for meet %s",
                             endpoint, len(data) if isinstance(data, list) else 1, meet_id)
                return data if isinstance(data, list) else [data]
        except requests.RequestException as exc:
            logger.warning("ScoreCat request failed for meet %s: %s", meet_id, exc)
        except ValueError as exc:
            logger.warning("ScoreCat returned non-JSON for meet %s: %s", meet_id, exc)

    return None


def run_live_polling(meet_id: str, stop_event=None) -> None:
    """
    Poll ScoreCat continuously until stop_event is set or meet ends.

    Args:
        meet_id: ScoreCat meetId string
        stop_event: threading.Event — set it to stop polling
    """
    from core.normalizer import normalize_scorecat_record
    from core.hasher import is_duplicate, mark_seen

    logger.info("Starting ScoreCat live polling for meet %s (interval=%ds)",
                meet_id, POLL_INTERVAL)

    while True:
        if stop_event and stop_event.is_set():
            logger.info("Stop event set — ending ScoreCat polling for meet %s", meet_id)
            break

        raw_records = poll_scorecat(meet_id)

        if raw_records:
            new_count = 0
            for raw in raw_records:
                try:
                    normalized = normalize_scorecat_record(raw)
                    if not is_duplicate(normalized):
                        mark_seen(normalized)
                        yield_or_store(normalized)
                        new_count += 1
                except Exception as exc:
                    logger.error("Error processing ScoreCat record: %s | raw=%s", exc, raw)
            if new_count:
                logger.info("ScoreCat meet %s: %d new records", meet_id, new_count)

        time.sleep(POLL_INTERVAL)


def yield_or_store(normalized: Dict) -> None:
    """
    Placeholder: in production, write to DB via SQLAlchemy session.
    For now, just log the record.
    """
    logger.info("New score: %s | %s | %s = %.3f",
                normalized.get("athlete_name"),
                normalized.get("event"),
                normalized.get("meet_id"),
                normalized.get("score", 0.0))
