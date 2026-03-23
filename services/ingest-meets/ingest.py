# -*- coding: utf-8 -*-
"""
Ingest Script - State-Focused Discovery

Two modes:
1. Auto-discovery: Discovers meets from MSO for specified states, saves to database, then scrapes scores
2. Target meets: Uses hardcoded TARGET_MEETS array (legacy mode)

Usage:
    # Auto-discovery mode (default) - scrapes first N meets
    .venv/bin/python ingest.py --disc [--states IN OH MI CA] [--scrape-limit 5]  # discover meets from MSO
    
    # Interactive mode - shows all meets and lets you select which to scrape
    .venv/bin/python ingest.py --interactive [--states IN OH MI CA]
    
    # Use hardcoded TARGET_MEETS array (no MSO listing requests unless --disc)
    .venv/bin/python ingest.py --use-target-meets [--scrape-limit 5]
    .venv/bin/python ingest.py --use-target-meets --disc   # merge metadata from MSO state/search listings
    
    # Interactive selection from TARGET_MEETS
    .venv/bin/python ingest.py --use-target-meets --interactive
    
    # Scrape single meet
    .venv/bin/python ingest.py --meet MSO-36189
"""

import argparse
from agents.mso_scraper import scrape_mso_meet, audit_duplicate_hashes, deduplicate_rows
import logging
import os
import sys
import re
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.exc import IntegrityError


from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("ingest")

# MSO "API" frequently returns HTML; default to skipping it in live polling.
MSO_API_ENABLED = os.getenv("MSO_API_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
# When true, do not use MSO page fingerprint to skip scrapes (always run full scrape).
MSO_DISABLE_RESULT_FINGERPRINT = os.getenv("MSO_DISABLE_RESULT_FINGERPRINT", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# If >0, run a full scrape anyway when the fingerprint matches but last_changed_at is older than
# this many minutes (live meets: scores can change without invalidating a flaky fingerprint).
def _fingerprint_force_scrape_minutes() -> int:
    raw = os.getenv("MSO_FINGERPRINT_FORCE_SCRAPE_MINUTES", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


# When true (default), do not fingerprint-skip if today's calendar date (MSO_TZ) falls within
# the meet's start_date..end_date in the DB — full scrape every run on competition days.
MSO_ALWAYS_SCRAPE_ON_MEET_DAYS = os.getenv("MSO_ALWAYS_SCRAPE_ON_MEET_DAYS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def _mso_tz_name() -> str:
    return os.getenv("MSO_TZ", "America/New_York").strip() or "America/New_York"


def _calendar_today_mso_tz():
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(_mso_tz_name())).date()
    except Exception:
        return datetime.utcnow().date()


def _is_within_meet_date_window(start, end) -> bool:
    if start is None:
        return False
    today = _calendar_today_mso_tz()
    last = end if end is not None else start
    return start <= today <= last


# Optional: enable target-list metadata merge without CLI --disc (default off; prefer --disc).
ENABLE_TARGET_METADATA_ENRICHMENT = os.getenv("ENABLE_TARGET_METADATA_ENRICHMENT", "0").strip().lower() in {
    "1", "true", "yes", "on",
}

# DB row `ingest_settings.key` — truthy values: 1, true, yes, on (toggle without changing Cloud Run args).
INGEST_SETTING_DISCOVER_MSO_LISTINGS = "discover_mso_listings"

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Run meet ingest for target meets")
parser.add_argument(
    "--scrape-limit",
    type=int,
    default=1,
    help=(
        "Stop after this many meets that return at least one score row (after dedup). "
        "Meets with no URL, fingerprint skip, errors, or 0 rows do not count. "
        "Not applied with --meet or --interactive (default: 5)"
    ),
)
parser.add_argument(
    "--meet",
    type=str,
    default=None,
    help="Scrape a single meet by meet_id (e.g. MSO-SWING-2026)",
)
parser.add_argument(
    "--use-target-meets",
    action="store_true",
    help="Use hardcoded TARGET_MEETS array instead of auto-discovery",
)
parser.add_argument(
    "--states",
    type=str,
    nargs="+",
    default=["IN", "OH", "MI", "CA"],
    help="State codes for meet discovery (default: IN OH MI CA). Used with --disc (and without --use-target-meets), or as fallback states for --disc + --use-target-meets.",
)
parser.add_argument(
    "--interactive",
    action="store_true",
    help="Show interactive menu to select which meets to scrape",
)
parser.add_argument(
    "--disc",
    action="store_true",
    help=(
        "Run MSO meet discovery (HTTP listing pages). With --use-target-meets: merge dates/location "
        "into TARGET_MEETS before save. Without --use-target-meets: build meet list from discovery "
        "(required in that mode)."
    ),
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Imports (after env is loaded)
# ---------------------------------------------------------------------------

from agents.mso_api_scraper import scrape_mso_meet_api
from agents.mso_scraper import (
    DEFAULT_UA,
    canonical_mso_url,
    fingerprint_mso_results_page_with_context,
    get_chromium_launch_kwargs,
    scrape_mso_meet,
    scrape_mso_meet_with_context,
)
from agents.meet_discovery import discover_meets
from core.normalizer import normalize_mso_record, normalize_mso_api_record
from core.gym_normalizer import normalize_gym_name as normalize_gym_name_canonical
from db.database import SessionLocal, create_tables, engine
from db.models import Meet, Athlete, AthleteAlias, Score, Gym, IngestSourceState, Session, IngestSetting
import hashlib

# ---------------------------------------------------------------------------
# Target meets - 2025-26 season, IN/KY/OH/MI focus
# From the gym schedule: Bug Bite through Walk of Fame
# ---------------------------------------------------------------------------

# Target meets for scraping (12 meets, excluding Tulip City which is not available via API)
# All meets use the new MSO API scraper which includes placement data
TARGET_MEETS = [
    # Each entry is upserted to the DB when using --use-target-meets (step 1) before scraping scores.
    # --- Already discovered / in DB ---
    # {
    #     "meet_id": "MSO-35799",
    #     "name": "2026 Jaycie Phelps Midwest Showdown",
    #     "mso_url": "https://www.meetscoresonline.com/R35799",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-23",
    #     "end_date": "2026-01-25",
    #     "location": "French Lick, IN",
    # },
    {
        "meet_id": "MSO-35397",
        "name": "2025 North Pole Classic USAG",
        "mso_url": "https://www.meetscoresonline.com/R35397",
        "source": "file", "state": "IN",
        "start_date": "2025-12-12", "location": "Indianapolis, IN",
    },
    # {
    #     "meet_id": "MSO-35120",
    #     "name": "2026 California Grand Invitational",
    #     "mso_url": "https://www.meetscoresonline.com/R35120",
    #     "source": "mso", "state": "CA",
    #     "start_date": "2026-01-09", "location": "Anaheim, CA",
    # },
    {
        "meet_id": "MSO-35846",
        "name": "2026 Jaycie Phelps Midwest Showdown NGA",
        "mso_url": "https://www.meetscoresonline.com/R35846",
        "source": "mso", "state": "IN",
        "start_date": "2026-01-23", "location": "French Lick, IN",
    },
    # {
    #     "meet_id": "MSO-35550",
    #     "name": "2026 Circle of Stars",
    #     "mso_url": "https://www.meetscoresonline.com/R35550",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-30", "location": "Indianapolis, IN",
    # },
    # {
    #     "meet_id": "MSO-35547",
    #     "name": "2026 Walk of Fame Classic",
    #     "mso_url": "https://www.meetscoresonline.com/R35547",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-07", "location": "Fort Wayne, IN",
    # },
    # {
    #     "meet_id": "MSO-36189",
    #     "name": "2026 Flip For Your Cause [USAG]",
    #     "mso_url": "https://www.meetscoresonline.com/R36189",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-20", "location": "Westfield, IN",
    # },
    {
        "meet_id": "MSO-36190",
        "name": "2026 Flip For Your Cause [NGA]",
        "mso_url": "https://www.meetscoresonline.com/R36190",
        "source": "mso", "state": "IN",
        "start_date": "2026-02-20", "location": "Westfield, IN",
    },
    {
        "meet_id": "MSO-36315",
        "name": "2026 Shamrock Shenanigans At Midwest",
        "mso_url": "https://www.meetscoresonline.com/R36315",
        "source": "mso", "state": "IN",
        "start_date": "2026-02-27", "location": "Dyer, IN",
    },
    # --- Need to find / verify MSO IDs ---
    # {
    #     "meet_id": "MSO-BUG-BITE-2025",
    #     "name": "2025 Bug Bite Invitational",
    #     "mso_url": "https://www.meetscoresonline.com/2025-IN-Bug-Bite-Invitational",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2025-11-15", "location": "Bloomington, IN",
    # },
    # Tulip City excluded - not available via API
    # {
    #     "meet_id": "MSO-TULIP-2026",
    #     "name": "2026 Tulip City Classic",
    #     "mso_url": "https://www.meetscoresonline.com/2026-MI-Tulip-City-Classic",
    #     "source": "file", "state": "MI",
    #     "start_date": "2026-02-06", "location": "Holland, MI",
    # },
    # {
    #     "meet_id": "MSO-DERBY-2026",
    #     "name": "2026 Derby Classic",
    #     "mso_url": "https://www.meetscoresonline.com/2026-KY-Derby-Classic",
    #     "source": "mso", "state": "KY",
    #     "start_date": "2026-02-27", "location": "Louisville, KY",
    # },
    # {
    #     "meet_id": "MSO-SWING-2026",
    #     "name": "2026 Swing Into Spring Invitational",
    #     "mso_url": "https://www.meetscoresonline.com/Results/36233",
    #     "source": "file", "state": "OH",
    #     "start_date": "2026-02-27", "location": "Hamilton, OH",
    # },
    {
        "meet_id": "MSO-36478",
        "name": "2026 IN Compulsory State Championships",
        "mso_url": "https://www.meetscoresonline.com/Results/36478",
        # "mso_url": "https://www.meetscoresonline.com/2026-IN-Compulsory-State-Championships",
        "source": "mso", "state": "IN",
        "start_date": "2026-03-13",
        "end_date": "2026-03-15",
        "location": "Crown Pointe, IN",
    },
    {
        "meet_id": "MSO-36489",
        "name": "2026 I AM Classic Meet",
        "mso_url": "https://www.meetscoresonline.com/R36489",
        "source": "mso", "state": "IN",
        "start_date": "2026-03-13",
        "end_date": "2026-03-14",
        "location": "Plymouth, IN",
    },
    {
        "meet_id": "MSO-36541",
        "name": "2026 Indiana Optional State Championships",
        "mso_url": "https://meetscoresonline.com/Results/36541",
        "source": "mso", "state": "IN",
        "start_date": "2026-03-20",
        "end_date": "2026-03-22",
        "location": "Bloomington, IN",
    },
    # {
    #     "meet_id": "MSO-36105",
    #     "name": "Money Madness 2026 - NGA",
    #     "mso_url": "https://www.meetscoresonline.com/R36105",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-13", "location": "Indianapolis, IN",
    # },
    # {
    #     "meet_id": "MSO-36116",
    #     "name": "Money Madness 2026 - USAG",
    #     "mso_url": "https://www.meetscoresonline.com/R36116",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-13", "location": "Indianapolis, IN",
    # },
    # {
    #     "meet_id": "MSO-35712",
    #     "name": "2026 MMUS USAG",
    #     "mso_url": "https://www.meetscoresonline.com/R35712",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-16", "location": "Indianapolis, IN",
    # },
    # {
    #     "meet_id": "MSO-35732",
    #     "name": "2026 MMUS NGA",
    #     "mso_url": "https://www.meetscoresonline.com/R35732",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-16", "location": "Indianapolis, IN",
    # },
    {
        "meet_id": "MSO-35610",
        "name": "2026 Wabash Valley Classic Meet NGA",
        "mso_url": "https://www.meetscoresonline.com/R35610",
        "source": "mso", "state": "IN",
        "start_date": "2026-01-09", "location": "Terre Haute, IN",
    },
    # {
    #     "meet_id": "MSO-35628",
    #     "name": "2026 Wabash Valley Classic Meet USAG",
    #     "mso_url": "https://www.meetscoresonline.com/R35628",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-09", "location": "Terre Haute, IN",
    # },
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_EXCLUDE_KEYWORDS = [
    "high school", "ihsaa", "ohsaa", " hs ", "hs session", "scholastic",
    "mock meet", "mock", "intersquad",
    "boys", "men's", "mens", " men", "mag ",
]

def _is_excluded_meet(name: str) -> bool:
    """Return True if the meet name matches an exclusion keyword (HS, mock, men's)."""
    lower = name.lower()
    return any(kw in lower for kw in _EXCLUDE_KEYWORDS)


def save_meets(meets: list) -> tuple:
    """
    Upsert meets into the database. Returns (inserted, skipped) counts.
    Automatically skips high school, mock, and men's meets.
    """
    create_tables()
    db = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        for m in meets:
            meet_id = m.get("meet_id")
            if not meet_id:
                continue

            if _is_excluded_meet(m.get("name", "")):
                logger.info("Skipping excluded meet: %s", m.get("name"))
                skipped += 1
                continue

            existing = db.query(Meet).filter(Meet.meet_id == meet_id).first()
            if existing:
                # Always update date/location/url in case they were missing before
                existing.start_date = _parse_date(m.get("start_date")) or existing.start_date
                existing.end_date = _parse_date(m.get("end_date")) or existing.end_date
                existing.location = m.get("location") or existing.location
                existing.facility = m.get("facility") or existing.facility
                existing.host_gym = m.get("host_gym") or existing.host_gym
                existing.state = m.get("state") or existing.state
                if m.get("mso_url"):
                    existing.mso_url = canonical_mso_url(str(m.get("mso_url")).strip())
                skipped += 1
                continue

            meet = Meet(
                meet_id=meet_id,
                name=m.get("name", "Unknown Meet"),
                state=m.get("state"),
                location=m.get("location"),
                facility=m.get("facility"),
                start_date=_parse_date(m.get("start_date")),
                end_date=_parse_date(m.get("end_date")),
                host_gym=m.get("host_gym"),
                mso_url=(
                    canonical_mso_url(str(m["mso_url"]).strip())
                    if m.get("mso_url")
                    else None
                ),
                scorecat_url=m.get("scorecat_url"),
                website_url=m.get("website_url"),
            )
            db.add(meet)
            inserted += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Database save failed: %s", exc)
        raise
    finally:
        db.close()

    return inserted, skipped


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def _calculate_placements_from_scores(normalized_rows: list, meet_id: str) -> list:
    """
    Calculate placements from scores when placement data is missing.
    Groups by session, level, division, and event, then ranks by score (higher = better).
    Only fills place for rows where place is None (does not overwrite MSO places).
    Uses competition ranking for ties (e.g. 1, 1, 3).
    """
    missing_places = sum(1 for row in normalized_rows if row.get("place") is None)
    if missing_places == 0:
        return normalized_rows

    logger.info("Calculating placements for %d scores missing place data (meet: %s)", missing_places, meet_id)

    from collections import defaultdict

    groups = defaultdict(list)
    for idx, row in enumerate(normalized_rows):
        key = (
            str(row.get("session") or ""),
            row.get("level", ""),
            row.get("division", ""),
            row.get("event", ""),
        )
        groups[key].append((idx, row))

    for _key, rows_with_idx in groups.items():
        sorted_rows = sorted(
            rows_with_idx,
            key=lambda x: (x[1].get("score") is None, -(x[1].get("score") or 0), x[1].get("athlete_name") or ""),
        )
        i = 0
        while i < len(sorted_rows):
            orig_idx, row = sorted_rows[i]
            sc = row.get("score")
            if sc is None:
                i += 1
                continue
            j = i + 1
            while j < len(sorted_rows) and sorted_rows[j][1].get("score") == sc:
                j += 1
            rank = i + 1
            for k in range(i, j):
                oi, r = sorted_rows[k]
                if r.get("place") is None:
                    normalized_rows[oi]["place"] = rank
            i = j

    calculated_count = sum(1 for row in normalized_rows if row.get("place") is not None)
    logger.info("Calculated placements for %d scores", calculated_count)

    return normalized_rows


def _get_or_create_gym(db, gym_name: str) -> Gym:
    """
    Get existing gym or create a new one.
    
    Uses canonical gym name normalization to prevent duplicates from variations
    like "Tfz" vs "The Flip Zone". Always checks canonical_name for matching.
    
    Args:
        db: Database session
        gym_name: Raw gym name from source
        
    Returns:
        Gym record (existing or newly created)
    """
    # Normalize to canonical name using mapping
    canonical = normalize_gym_name_canonical(gym_name)
    
    # Always search by canonical_name to prevent duplicates
    gym = db.query(Gym).filter(Gym.canonical_name == canonical).first()
    if not gym:
        gym = Gym(name=canonical, canonical_name=canonical)
        db.add(gym)
        db.flush()
        logger.info("Created new gym: %s (canonical: %s)", gym_name, canonical)
    
    return gym


def _get_or_create_athlete(db, athlete_name: str, gym: Gym, level: str = None) -> Athlete:
    """
    Get existing athlete by alias or create new one.
    
    CRITICAL: Matching is ALWAYS scoped to name + gym_id to prevent duplicates.
    This ensures:
    - Same athlete name at different gyms = different athlete records (correct)
    - Same athlete name at same gym = same athlete record (prevents duplicates)
    - Same athlete at different levels at same gym = same athlete record (allows level changes)
    
    The level field can change over time (athlete moves up levels), but the
    athlete record itself is identified by name + gym_id combination.
    
    Args:
        db: Database session
        athlete_name: Raw athlete name from source
        gym: Gym record (must be canonical, normalized gym)
        level: Optional level string
        
    Returns:
        Athlete record (existing or newly created), or None if name is invalid
    """
    if not athlete_name:
        return None
    raw_name = athlete_name.strip()
    
    if not gym:
        logger.warning("Cannot create athlete '%s' without gym", raw_name)
        return None

    # Check alias table first - scoped to same gym
    alias = (
        db.query(AthleteAlias)
        .join(Athlete)
        .filter(
            AthleteAlias.raw_name == raw_name,
            Athlete.gym_id == gym.id,  # Always require gym match
        )
        .first()
    )
    if alias:
        # Update level if provided and different (athlete may have moved up)
        if level and alias.athlete.level != level:
            alias.athlete.level = level
            db.flush()
        return alias.athlete

    # Check canonical name scoped to same gym
    athlete = (
        db.query(Athlete)
        .filter(
            Athlete.canonical_name == raw_name,
            Athlete.gym_id == gym.id,  # Always require gym match
        )
        .first()
    )
    if not athlete:
        athlete = Athlete(
            canonical_name=raw_name,
            gym_id=gym.id,
            level=level,
        )
        db.add(athlete)
        db.flush()
        logger.debug("Created new athlete: %s at gym %s (ID: %d)", raw_name, gym.canonical_name, gym.id)

    # Record the alias (skip if already exists)
    existing_alias = (
        db.query(AthleteAlias)
        .filter(
            AthleteAlias.athlete_id == athlete.id,
            AthleteAlias.raw_name == raw_name,
        )
        .first()
    )
    if not existing_alias:
        alias = AthleteAlias(athlete_id=athlete.id, raw_name=raw_name, source="mso_api")
        db.add(alias)
        db.flush()
    
    return athlete


def save_scores(normalized_rows: list, meet_external_id: str) -> tuple:
    """
    Save normalized score rows to the database.
    Saves AA + individual events (VT, UB, BB, FX) as separate score rows.
    Creates Gym, Athlete, AthleteAlias, and Score records as needed.
    Skips duplicate scores using record_hash.
    
    DUPLICATE PREVENTION:
    - Gyms: Uses canonical gym name mapping (core.gym_normalizer) to prevent
      duplicates from variations like "Tfz" vs "The Flip Zone"
    - Athletes: Always scoped to name + gym_id combination to prevent duplicates
      while allowing same name at different gyms
    - Scores: Uses record_hash based on meet_id + athlete_name + event + score
    
    Returns (inserted, skipped) counts.
    """
    db = SessionLocal()
    inserted = 0
    skipped = 0

    session_cache: dict[tuple[Optional[int], Optional[datetime]], Optional[Session]] = {}

    def _parse_session_metadata(raw: str) -> tuple[Optional[int], Optional[datetime]]:
        """
        Best-effort mapping from scraper session label -> (session_number, start_time).
        This is intentionally tolerant because MSO session labels vary across meets.
        """
        if not raw:
            return None, None

        s = str(raw).strip()

        # 1) Session number like "Session 01" or "Session 1"
        m = re.search(r"Session\s*0*(\d+)", s, flags=re.IGNORECASE)
        session_number: Optional[int] = int(m.group(1)) if m else None

        # 2) Date like M/D/YYYY (also found in "Saturday 3/14/2026")
        date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        start_time: Optional[datetime] = None
        if date_match:
            mm, dd, yyyy = (int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            # 24h time parsing if present, otherwise midnight
            time_match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", s, flags=re.IGNORECASE)
            if time_match:
                hh = int(time_match.group(1))
                minutes = int(time_match.group(2))
                ampm = time_match.group(3).upper()
                if ampm == "PM" and hh != 12:
                    hh += 12
                if ampm == "AM" and hh == 12:
                    hh = 0
                start_time = datetime(yyyy, mm, dd, hh, minutes)
            else:
                start_time = datetime(yyyy, mm, dd, 0, 0)

        # 3) Many MSO session picker labels look like "01A", "02B", etc.
        # Extract the leading digits even if the next char is a letter (no word boundary).
        if session_number is None:
            m2 = re.match(r"^\s*0*(\d+)", s)
            if m2:
                session_number = int(m2.group(1))

        return session_number, start_time

    def _get_or_create_session(
        db,
        *,
        meet_db_id: int,
        session_key: str,
        session_number: Optional[int],
        start_time: Optional[datetime],
    ) -> Optional[Session]:
        # If the scraper didn't give us anything useful, keep the FK null.
        if not session_key:
            return None

        cache_key = (session_number, start_time)
        if cache_key in session_cache:
            return session_cache[cache_key]

        q = db.query(Session).filter(Session.meet_id == meet_db_id)
        if session_number is None:
            q = q.filter(Session.session_number.is_(None))
        else:
            q = q.filter(Session.session_number == session_number)

        if start_time is None:
            q = q.filter(Session.start_time.is_(None))
        else:
            q = q.filter(Session.start_time == start_time)

        sess = q.first()
        if not sess:
            sess = Session(meet_id=meet_db_id, session_number=session_number, start_time=start_time)
            db.add(sess)
            db.flush()

        session_cache[cache_key] = sess
        return sess

    # Individual event columns in the normalized row → event label
    EVENT_FIELDS = {
        "vault":  "VT",
        "bars":   "UB",
        "beam":   "BB",
        "floor":  "FX",
        "pommel": "PH",
        "rings":  "SR",
        "pbars":  "PB",
        "hibar":  "HB",
    }

    try:
        meet = db.query(Meet).filter(Meet.meet_id == meet_external_id).first()
        if not meet:
            logger.warning("Meet %s not found in DB - skipping scores", meet_external_id)
            db.close()
            return 0, 0

        # Build a lightweight plan first (no DB lookups besides `meet`), then bulk-check hashes.
        planned = []
        all_hashes: list[str] = []

        for row in normalized_rows:
            athlete_name = row.get("athlete_name", "").strip()
            if not athlete_name:
                skipped += 1
                continue

            gym_name = row.get("gym", "").strip()
            level = row.get("level")
            division = row.get("division")
            session_key = str(row.get("session") or "").strip()
            session_number, session_start_time = _parse_session_metadata(session_key)

            events_to_save = []

            event = row.get("event")
            if event:
                score_val = row.get("score")
                place = row.get("place")
                if score_val is not None:
                    events_to_save.append((event, score_val, place))
            else:
                aa_score = row.get("score")
                if aa_score is not None:
                    events_to_save.append(("AA", aa_score, row.get("place")))

                event_place_map = {
                    "vault": ("VT", "vault_place"),
                    "bars": ("UB", "bars_place"),
                    "beam": ("BB", "beam_place"),
                    "floor": ("FX", "floor_place"),
                }
                for field, (label, place_key) in event_place_map.items():
                    val = row.get(field)
                    if val is not None:
                        events_to_save.append((label, val, row.get(place_key)))

            # Precompute record_hashes without touching the DB.
            hashes = []
            for event_label, score_val, _place in events_to_save:
                # Include session in the hash only when we actually have a session label.
                # This prevents different session-days from collapsing into the same row.
                if session_key:
                    hash_input = f"{meet.id}|{athlete_name}|{event_label}|{score_val}|{session_key}"
                else:
                    hash_input = f"{meet.id}|{athlete_name}|{event_label}|{score_val}"
                h = hashlib.sha256(hash_input.encode()).hexdigest()
                hashes.append(h)
                all_hashes.append(h)

            planned.append(
                {
                    "athlete_name": athlete_name,
                    "gym_name": gym_name,
                    "level": level,
                    "division": division,
                    "source": row.get("source", "mso"),
                    "session_key": session_key,
                    "session_number": session_number,
                    "session_start_time": session_start_time,
                    "events": events_to_save,
                    "hashes": hashes,
                }
            )

        if not all_hashes:
            return 0, skipped

        # Load existing score rows by hash so we can UPDATE place when MSO adds it later (same score → same hash).
        unique_hashes = list(set(all_hashes))
        existing_score_rows: dict[str, Score] = {}
        CHUNK = 900
        for off in range(0, len(unique_hashes), CHUNK):
            chunk = unique_hashes[off : off + CHUNK]
            for sc in db.query(Score).filter(Score.record_hash.in_(chunk)).all():
                existing_score_rows[sc.record_hash] = sc

        seen_hashes_in_batch: set[str] = set()

        for plan in planned:
            gym = None
            athlete = None
            session_obj = None
            abort_plan_inserts = False

            for (event_label, score_val, place), record_hash in zip(plan["events"], plan["hashes"]):
                if record_hash in seen_hashes_in_batch:
                    skipped += 1
                    continue

                existing_row = existing_score_rows.get(record_hash)
                if existing_row is not None:
                    seen_hashes_in_batch.add(record_hash)
                    if place is not None and existing_row.place != place:
                        existing_row.place = place
                        inserted += 1
                    else:
                        skipped += 1
                    continue

                if abort_plan_inserts:
                    skipped += 1
                    continue

                if gym is None:
                    gym = _get_or_create_gym(db, plan["gym_name"])
                if athlete is None:
                    athlete = _get_or_create_athlete(db, plan["athlete_name"], gym, plan["level"])
                if not athlete:
                    abort_plan_inserts = True
                    skipped += 1
                    continue

                if session_obj is None:
                    session_obj = _get_or_create_session(
                        db,
                        meet_db_id=meet.id,
                        session_key=plan.get("session_key") or "",
                        session_number=plan.get("session_number"),
                        start_time=plan.get("session_start_time"),
                    )

                seen_hashes_in_batch.add(record_hash)

                score = Score(
                    athlete_id=athlete.id,
                    meet_id=meet.id,
                    session_id=session_obj.id if session_obj else None,
                    event=event_label,
                    score=score_val,
                    place=place,
                    level=plan["level"],
                    division=plan["division"],
                    source=plan["source"],
                    record_hash=record_hash,
                )
                db.add(score)
                existing_score_rows[record_hash] = score
                inserted += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Score save failed: %s", exc)
        raise
    finally:
        db.close()

    return inserted, skipped


# ---------------------------------------------------------------------------
# Interactive Selection
# ---------------------------------------------------------------------------

def check_meet_sources(meet: dict, db_session=None) -> dict:
    """Check what data sources are available for a meet and if it has existing data."""
    sources = {
        "mso_url": bool(meet.get("mso_url")),
        "website_url": bool(meet.get("website_url")),
        "scorecat_url": bool(meet.get("scorecat_url")),
        "has_data": False,
        "score_count": 0,
    }
    
    # Check if meet has existing scores in database
    if db_session:
        try:
            from db.models import Meet, Score
            meet_record = db_session.query(Meet).filter(
                Meet.meet_id == meet.get("meet_id")
            ).first()
            if meet_record:
                score_count = db_session.query(Score).filter(
                    Score.meet_id == meet_record.id
                ).count()
                sources["has_data"] = score_count > 0
                sources["score_count"] = score_count
        except Exception:
            pass  # If DB check fails, just skip it
    
    return sources


def format_sources(sources: dict) -> str:
    """Format sources as a string indicator."""
    parts = []
    if sources["mso_url"]:
        parts.append("MSO")
    if sources["website_url"]:
        parts.append("Website")
    if sources["scorecat_url"]:
        parts.append("ScoreCat")
    
    source_str = ", ".join(parts) if parts else "None"
    
    # Add data status
    if sources["has_data"]:
        source_str += f" | {sources['score_count']} scores in DB"
    else:
        source_str += " | No data yet"
    
    return source_str


def _merge_missing_meet_metadata(base_meets: list[dict], discovered_meets: list[dict]) -> list[dict]:
    """
    Fill missing metadata on base meets using discovered meets.
    Match by meet_id first, then by normalized mso_url.
    """
    by_id = {m.get("meet_id"): m for m in discovered_meets if m.get("meet_id")}
    by_url = {
        str(canonical_mso_url(str(m["mso_url"]).strip())).lower(): m
        for m in discovered_meets
        if m.get("mso_url")
    }
    fields = ["start_date", "end_date", "location", "facility", "host_gym", "state"]

    merged: list[dict] = []
    for m in base_meets:
        out = dict(m)
        src = by_id.get(out.get("meet_id"))
        if not src and out.get("mso_url"):
            src = by_url.get(
                str(canonical_mso_url(str(out["mso_url"]).strip())).lower()
            )
        if src:
            for f in fields:
                if not out.get(f) and src.get(f):
                    out[f] = src.get(f)
        merged.append(out)
    return merged


def interactive_meet_selection(meets: list) -> list:
    """Show interactive menu to select meets to scrape."""
    if not meets:
        print("  No meets found to select from.")
        return []
    
    print(f"\n{'='*80}")
    print(f"  Found {len(meets)} meets. Checking data sources...")
    print(f"{'='*80}\n")
    
    # Get database session to check for existing data
    db = None
    try:
        db = SessionLocal()
    except Exception:
        pass  # If DB connection fails, continue without data checks
    
    # Display meets with their sources
    for i, meet in enumerate(meets, 1):
        sources = check_meet_sources(meet, db_session=db)
        sources_str = format_sources(sources)
        name = meet.get("name", meet.get("meet_id", "Unknown"))
        state = meet.get("state", "?")
        date = meet.get("start_date", "?")
        location = meet.get("location", "")
        
        # Highlight meets with data
        data_indicator = "✓" if sources["has_data"] else "○"
        
        print(f"  [{i:2d}] {data_indicator} {name}")
        print(f"       ID: {meet.get('meet_id', 'N/A')} | State: {state} | Date: {date}")
        if location:
            print(f"       Location: {location}")
        print(f"       Sources: {sources_str}")
        print()
    
    if db:
        db.close()
    
    print(f"{'='*80}")
    print("\nEnter meet numbers to scrape (comma-separated, e.g., 1,3,5-7,10)")
    print("Or 'all' to scrape all meets, or 'none' to skip:")
    
    selection = input("Selection: ").strip().lower()
    
    if selection == "none":
        return []
    elif selection == "all":
        return meets
    
    # Parse selection
    selected_indices = set()
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            # Range like "5-7"
            try:
                start, end = part.split("-", 1)
                start_idx = int(start.strip()) - 1
                end_idx = int(end.strip())
                selected_indices.update(range(start_idx, end_idx))
            except ValueError:
                print(f"  Warning: Invalid range '{part}', skipping")
        else:
            # Single number
            try:
                idx = int(part) - 1
                if 0 <= idx < len(meets):
                    selected_indices.add(idx)
                else:
                    print(f"  Warning: Index {part} out of range, skipping")
            except ValueError:
                print(f"  Warning: Invalid number '{part}', skipping")
    
    selected_meets = [meets[i] for i in sorted(selected_indices)]
    print(f"\n  Selected {len(selected_meets)} meet(s) to scrape.\n")
    return selected_meets


def _truthy_ingest_setting(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _discover_mso_listings_enabled_via_db() -> bool:
    try:
        create_tables()
        db = SessionLocal()
        try:
            row = (
                db.query(IngestSetting)
                .filter(IngestSetting.key == INGEST_SETTING_DISCOVER_MSO_LISTINGS)
                .first()
            )
            return _truthy_ingest_setting(row.value) if row else False
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Could not read ingest_settings.%s: %s", INGEST_SETTING_DISCOVER_MSO_LISTINGS, exc)
        return False


def _resolve_discover_mso_listings(args) -> tuple[bool, str]:
    """Whether to run discover_meets() (MSO listing HTTP). Returns (enabled, source label for logs)."""
    if getattr(args, "disc", False):
        return True, "disc"
    if ENABLE_TARGET_METADATA_ENRICHMENT:
        return True, "ENABLE_TARGET_METADATA_ENRICHMENT"
    if _discover_mso_listings_enabled_via_db():
        return True, f"ingest_settings.{INGEST_SETTING_DISCOVER_MSO_LISTINGS}"
    return False, "off"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Advisory lock key so only one ingest runs at a time (avoids overlapping Cloud Run executions).
_INGEST_LOCK_KEY = 9876543210


def _run_ingest_core(args) -> tuple[int, int]:
    """
    Core ingest logic shared by the CLI `main()` and programmatic `run_ingest`.

    Returns:
        (score_rows_total, score_saved_total)
    """
    # Concurrency guard: only one ingest at a time across all runners (e.g. Cloud Run Jobs).
    lock_conn = engine.raw_connection()
    lock_acquired = False
    try:
        cur = lock_conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_INGEST_LOCK_KEY,))
        if not cur.fetchone()[0]:
            lock_conn.close()
            print("Another ingest is already running, exiting.")
            return 0, 0
        lock_acquired = True
    except Exception as e:
        lock_conn.close()
        logger.warning("Could not acquire ingest lock (non-Postgres?): %s", e)
        # Proceed without lock if DB doesn't support it

    try:
        print(f"\n{'='*60}")
        print(f"  USAG Meet Tracker - Targeted Ingest")

        discover_mso, discover_src = _resolve_discover_mso_listings(args)

        # Step 0: Determine meets source
        if args.use_target_meets:
            print(f"  Mode: TARGET_MEETS (hardcoded list) — score scrape uses Playwright on each meet URL")
            meets_to_process = TARGET_MEETS
            print(f"  Meets: {len(meets_to_process)} entries in TARGET_MEETS")

            # Optional: HTTP crawl of MSO state/search listing pages (discover_meets), not the results scraper.
            if args.meet:
                print(
                    "  MSO listing discovery: skipped (--meet; no index/search crawl, only that meet’s results page)"
                )
            elif discover_mso:
                print(f"  MSO listing discovery: on ({discover_src}) — crawling MSO index/search to enrich metadata")
                try:
                    target_states = sorted(
                        {str(m.get("state")).upper() for m in meets_to_process if m.get("state")}
                    ) or args.states
                    discovered = discover_meets(states=target_states)
                    meets_to_process = _merge_missing_meet_metadata(meets_to_process, discovered)
                    print(
                        f"  MSO listing discovery: merged missing fields from {len(discovered)} listing rows "
                        f"(states: {', '.join(target_states)})"
                    )
                except Exception as exc:
                    print(f"  MSO listing discovery: failed ({exc})")
            else:
                print(
                    "  MSO listing discovery: off — no MSO /Results.All or ?search= HTTP crawl; "
                    "TARGET_MEETS unchanged before save. Turn on with --disc, ENABLE_TARGET_METADATA_ENRICHMENT=1, "
                    f"or DB ingest_settings.{INGEST_SETTING_DISCOVER_MSO_LISTINGS}=true"
                )
        else:
            print(
                "  Mode: MSO listing discovery only — meet list built from MSO index/search pages (not TARGET_MEETS)"
            )
            if not discover_mso:
                print("  ERROR: This mode needs MSO listing discovery enabled.")
                print("  Turn on: --disc, ENABLE_TARGET_METADATA_ENRICHMENT=1, or DB")
                print(f"  ingest_settings key {INGEST_SETTING_DISCOVER_MSO_LISTINGS!r} = true")
                print("  Or use:  python ingest.py --use-target-meets  (no listing crawl)")
                print("  Example:  python ingest.py --disc --states IN --scrape-limit 5")
                return 0, 0
            print(f"  MSO listing discovery: on ({discover_src}) — states: {', '.join(args.states)}")
            discovered_meets = discover_meets(states=args.states)
            meets_to_process = discovered_meets
            print(f"  MSO listing discovery: {len(discovered_meets)} meets returned from listing crawl")

        print(f"{'='*60}\n")

        # Step 1: Upsert all meets
        print(f"[1/2] Upsert meet rows to database (from TARGET_MEETS or listing crawl above)...")
        try:
            inserted, skipped = save_meets(meets_to_process)
            print(f"      Inserted: {inserted}  |  Already existed: {skipped}\n")
        except Exception as exc:
            print(f"      ERROR saving meets: {exc}\n")
            raise

        # Step 2: Select meets to scrape
        if args.meet:
            meets_to_scrape = [m for m in meets_to_process if m["meet_id"] == args.meet]
            if not meets_to_scrape:
                print(f"      ERROR: No meet found with meet_id '{args.meet}'")
                if args.use_target_meets:
                    print(f"      Available IDs: {[m['meet_id'] for m in TARGET_MEETS]}")
                return 0, 0
            print(f"      Targeting single meet: {args.meet}")
        elif args.interactive:
            meets_to_scrape = interactive_meet_selection(meets_to_process)
            if not meets_to_scrape:
                print("  No meets selected. Exiting.")
                return 0, 0
        else:
            # Full list: we stop after `scrape_limit` meets that return at least one score row
            # (after dedup). Meets with no MSO URL, fingerprint skip, errors, or 0 rows do not count.
            meets_to_scrape = meets_to_process

        if args.meet or args.interactive:
            print(
                f"[2/2] Results-page scrape (Playwright) for {len(meets_to_scrape)} selected meet(s)..."
            )
        else:
            print(
                f"[2/2] Results-page scrape (Playwright), up to {args.scrape_limit} meets **with data**; "
                f"0-row meets do not count toward the limit..."
            )

        score_rows_total = 0
        score_saved_total = 0

        use_success_based_limit = not args.meet and not args.interactive
        scrape_success_target = args.scrape_limit if use_success_based_limit else None
        successful_meets_with_rows = 0
        meet_queue = meets_to_scrape
        qi = 0

        while qi < len(meet_queue):
            if (
                scrape_success_target is not None
                and successful_meets_with_rows >= scrape_success_target
            ):
                break
            meet = meet_queue[qi]
            qi += 1
            i = qi - 1  # 0-based; existing logs use [{i+1}]
            mso_url = canonical_mso_url((meet.get("mso_url") or "").strip())
            name = meet.get("name", meet["meet_id"])
            if not mso_url:
                print(f"      [{i+1}] {name} - no MSO URL, skipping")
                continue

            # Big win: reuse the same Playwright context for fingerprint + scrape
            # so we don't pay browser startup twice on "changed" runs.
            pw = None
            browser = None
            context = None
            try:
                from playwright.sync_api import sync_playwright

                pw = sync_playwright().start()
                browser = None
                context = None

                def _new_browser_context() -> None:
                    nonlocal browser, context
                    if browser is not None:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    browser = pw.chromium.launch(**get_chromium_launch_kwargs())
                    context = browser.new_context(user_agent=DEFAULT_UA)

                _new_browser_context()

                # Cheap change detection: fingerprint the rendered results page.
                fp = None
                if not MSO_DISABLE_RESULT_FINGERPRINT:
                    try:
                        fp = fingerprint_mso_results_page_with_context(context, mso_url)
                    except Exception as exc:
                        logger.warning(
                            "MSO fingerprint failed (relaunching browser before scrape): %s",
                            exc,
                        )
                        fp = None
                        _new_browser_context()

                skip_due_to_no_change = False
                if fp:
                    db = SessionLocal()
                    try:
                        meet_row = db.query(Meet).filter(Meet.meet_id == meet["meet_id"]).first()
                        if meet_row:
                            now = datetime.utcnow()
                            state = (
                                db.query(IngestSourceState)
                                .filter(
                                    IngestSourceState.meet_id == meet_row.id,
                                    IngestSourceState.source == "mso_results",
                                )
                                .first()
                            )
                            if not state:
                                state = IngestSourceState(meet_id=meet_row.id, source="mso_results")
                                db.add(state)
                                db.flush()

                            if state.last_fingerprint == fp:
                                # Only skip unchanged fingerprints when this meet already has scores.
                                # If no scores exist yet, keep scraping to avoid "stuck at zero rows".
                                existing_score = (
                                    db.query(Score.id)
                                    .filter(Score.meet_id == meet_row.id)
                                    .first()
                                )
                                state.last_polled_at = now
                                db.commit()
                                force_mins = _fingerprint_force_scrape_minutes()
                                stale = False
                                if (
                                    force_mins > 0
                                    and existing_score
                                    and state.last_changed_at is not None
                                ):
                                    age_sec = (now - state.last_changed_at).total_seconds()
                                    if age_sec >= force_mins * 60:
                                        stale = True
                                if existing_score and not stale:
                                    if MSO_ALWAYS_SCRAPE_ON_MEET_DAYS and _is_within_meet_date_window(
                                        meet_row.start_date, meet_row.end_date
                                    ):
                                        print(
                                            f"      [{i+1}] {name} - fingerprint unchanged but today is within "
                                            f"meet dates ({meet_row.start_date}–{meet_row.end_date or meet_row.start_date}); "
                                            f"forcing full scrape"
                                        )
                                    else:
                                        print(f"      [{i+1}] {name} - no change detected, skipping")
                                        skip_due_to_no_change = True
                                elif existing_score and stale:
                                    print(
                                        f"      [{i+1}] {name} - fingerprint unchanged but "
                                        f"last successful scrape > {force_mins}m ago; forcing full scrape"
                                    )
                                else:
                                    print(
                                        f"      [{i+1}] {name} - fingerprint unchanged but no saved scores yet; retrying scrape"
                                    )
                            else:
                                # New fingerprint seen; mark poll time now.
                                # We promote last_fingerprint after a non-empty scrape below.
                                state.last_polled_at = now
                                db.commit()
                                skip_due_to_no_change = False
                    finally:
                        db.close()

                if skip_due_to_no_change:
                    continue

                # Try the API scraper only when explicitly enabled; otherwise go straight to HTML.
                raw_rows = scrape_mso_meet_api(mso_url) if MSO_API_ENABLED else []

                if raw_rows:
                    # API format: one row per athlete, needs expansion to one per event
                    normalized = []
                    for raw_row in raw_rows:
                        # Debug: show what we're getting from API
                        if len(normalized) == 0:  # Only log first athlete
                            logger.debug("Sample API row keys: %s", list(raw_row.keys()))
                            logger.debug(
                                "Sample API row scores: vault=%s, bars=%s, beam=%s, floor=%s, aa=%s",
                                raw_row.get("vault"),
                                raw_row.get("bars"),
                                raw_row.get("beam"),
                                raw_row.get("floor"),
                                raw_row.get("aa_score"),
                            )

                        expanded = normalize_mso_api_record(raw_row)
                        if isinstance(expanded, list):
                            normalized.extend(expanded)
                            if len(normalized) <= 5:
                                for exp in expanded:
                                    logger.debug(
                                        "  Expanded: event=%s, score=%s, place=%s",
                                        exp.get("event"),
                                        exp.get("score"),
                                        exp.get("place"),
                                    )
                        else:
                            normalized.append(expanded)
                else:
                    # Fallback to HTML scraper if API fails (returns empty or None)
                    if MSO_API_ENABLED:
                        logger.warning("API scraper returned no results, trying HTML scraper")
                    raw_rows = scrape_mso_meet_with_context(context, mso_url) if context else scrape_mso_meet(mso_url)
                    normalized = []
                    for raw_row in raw_rows:
                        expanded = normalize_mso_record(raw_row)
                        if isinstance(expanded, list):
                            normalized.extend(expanded)
                            if len(normalized) <= 5:
                                logger.info(
                                    "Expanded first athlete into %d records: %s",
                                    len(expanded),
                                    [(r.get("event"), r.get("score")) for r in expanded],
                                )
                        else:
                            normalized.append(expanded)

                # CRITICAL: Deduplicate normalized records BEFORE saving
                seen_normalized = {}
                deduplicated_normalized = []
                duplicates_removed = 0

                for row in normalized:
                    athlete_name = row.get("athlete_name", "").strip()
                    event = row.get("event", "")
                    score = row.get("score")
                    meet_external_id = meet["meet_id"]

                    if not athlete_name or score is None or score == 0:
                        continue

                    unique_key = f"{meet_external_id}|{athlete_name}|{event}|{score}"

                    if unique_key in seen_normalized:
                        duplicates_removed += 1
                        logger.debug(
                            "Duplicate normalized record: %s | %s | %s", athlete_name, event, score
                        )
                        continue

                    seen_normalized[unique_key] = True
                    deduplicated_normalized.append(row)

                if duplicates_removed > 0:
                    logger.warning("Removed %d duplicate normalized records before saving", duplicates_removed)

                normalized = deduplicated_normalized

                normalized = _calculate_placements_from_scores(normalized, meet["meet_id"])

                n = len(normalized)
                score_rows_total += n
                print(f"      [{i+1}] {name}")
                print(
                    f"            → {len(raw_rows)} athlete rows scraped → {n} score records (after dedup)"
                )

                if normalized:
                    events_by_type: dict[str, int] = {}
                    for row in normalized:
                        event = row.get("event", "UNKNOWN")
                        events_by_type[event] = events_by_type.get(event, 0) + 1

                    sample = normalized[0]
                    print(
                        f"            → sample: {sample.get('athlete_name')} | "
                        f"L{sample.get('level')} | {sample.get('event')}={sample.get('score')} "
                        f"| place={sample.get('place')} | div={sample.get('division')}"
                    )
                    print(f"            → events breakdown: {dict(events_by_type)}")

                    saved, dupes = save_scores(normalized, meet["meet_id"])
                    score_saved_total += saved
                    print(
                        f"            → saved: {saved} new score records  |  skipped: {dupes} dupes"
                    )

                    if scrape_success_target is not None:
                        successful_meets_with_rows += 1

                    # Promote fingerprint only after we actually scraped non-empty data.
                    if fp:
                        db = SessionLocal()
                        try:
                            meet_row = db.query(Meet).filter(Meet.meet_id == meet["meet_id"]).first()
                            if meet_row:
                                state = (
                                    db.query(IngestSourceState)
                                    .filter(
                                        IngestSourceState.meet_id == meet_row.id,
                                        IngestSourceState.source == "mso_results",
                                    )
                                    .first()
                                )
                                if not state:
                                    state = IngestSourceState(meet_id=meet_row.id, source="mso_results")
                                    db.add(state)
                                    db.flush()
                                now = datetime.utcnow()
                                state.last_fingerprint = fp
                                state.last_polled_at = now
                                state.last_changed_at = now
                                db.commit()
                        finally:
                            db.close()
                else:
                    print(f"            → no rows found (meet may not have results yet)")

            except Exception as exc:
                import traceback

                print(f"      [{i+1}] {name} - error: {exc}")
                logger.debug(traceback.format_exc())
            finally:
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass
                try:
                    if pw:
                        pw.stop()
                except Exception:
                    pass

        print(f"\n{'='*60}")
        print(f"  Done.")
        print(f"  Completed at       : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Score rows scraped  : {score_rows_total}")
        print(f"  Score records saved : {score_saved_total}")
        print(f"  (Each athlete row saves AA + up to 4 individual event scores)")
        print(f"{'='*60}\n")

        return score_rows_total, score_saved_total
    finally:
        if lock_acquired and lock_conn:
            try:
                cur = lock_conn.cursor()
                cur.execute("SELECT pg_advisory_unlock(%s)", (_INGEST_LOCK_KEY,))
            finally:
                lock_conn.close()


def run_ingest(
    *,
    meet_id: str | None = None,
    use_target_meets: bool = False,
    states: list[str] | None = None,
    scrape_limit: int = 5,
    interactive: bool = False,
    disc: bool | None = None,
) -> tuple[int, int]:
    """
    Programmatic entrypoint for ingestion (Cloud Run jobs, other apps, tests).

    When meet_id and interactive are both unset, scrape_limit is the number of meets
    that must return at least one score row (after dedup); 0-row meets are skipped
    for the count and scanning continues down the list.

    `disc`: if None, defaults to (not use_target_meets) so discovery mode still discovers;
    set False with use_target_meets to skip MSO listing requests.

    Returns (score_rows_total, score_saved_total).
    """
    if disc is None:
        disc = not use_target_meets

    class _Args:
        def __init__(self) -> None:
            self.scrape_limit = scrape_limit
            self.meet = meet_id
            self.use_target_meets = use_target_meets
            self.states = states or ["IN", "OH", "MI", "CA"]
            self.interactive = interactive
            self.disc = disc

    return _run_ingest_core(_Args())


def main() -> None:
    global args
    args = parser.parse_args()
    _run_ingest_core(args)


if __name__ == "__main__":
    main()