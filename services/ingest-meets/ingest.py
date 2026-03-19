# -*- coding: utf-8 -*-
"""
Ingest Script - State-Focused Discovery

Two modes:
1. Auto-discovery: Discovers meets from MSO for specified states, saves to database, then scrapes scores
2. Target meets: Uses hardcoded TARGET_MEETS array (legacy mode)

Usage:
    # Auto-discovery mode (default) - scrapes first N meets
    .venv/bin/python ingest.py [--states IN OH MI CA] [--scrape-limit 5]
    
    # Interactive mode - shows all meets and lets you select which to scrape
    .venv/bin/python ingest.py --interactive [--states IN OH MI CA]
    
    # Use hardcoded TARGET_MEETS array
    .venv/bin/python ingest.py --use-target-meets [--scrape-limit 5]
    
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
from datetime import datetime
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

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Run meet ingest for target meets")
parser.add_argument(
    "--scrape-limit",
    type=int,
    default=5,
    help="Max meets to attempt score scraping on (default: 5)",
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
    help="State codes for meet discovery (default: IN OH MI CA). Only used when --use-target-meets is not set.",
)
parser.add_argument(
    "--interactive",
    action="store_true",
    help="Show interactive menu to select which meets to scrape",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Imports (after env is loaded)
# ---------------------------------------------------------------------------

from agents.mso_api_scraper import scrape_mso_meet_api
from agents.mso_scraper import (
    DEFAULT_UA,
    fingerprint_mso_results_page_with_context,
    scrape_mso_meet,
    scrape_mso_meet_with_context,
)
from agents.meet_discovery import discover_meets
from core.normalizer import normalize_mso_record, normalize_mso_api_record
from core.gym_normalizer import normalize_gym_name as normalize_gym_name_canonical
from db.database import SessionLocal, create_tables, engine
from db.models import Meet, Athlete, AthleteAlias, Score, Gym, IngestSourceState, Session
import hashlib

# ---------------------------------------------------------------------------
# Target meets - 2025-26 season, IN/KY/OH/MI focus
# From the gym schedule: Bug Bite through Walk of Fame
# ---------------------------------------------------------------------------

# Target meets for scraping (12 meets, excluding Tulip City which is not available via API)
# All meets use the new MSO API scraper which includes placement data
TARGET_MEETS = [
    # --- Already discovered / in DB ---
    # {
    #     "meet_id": "MSO-35397",
    #     "name": "2025 North Pole Classic USAG",
    #     "mso_url": "https://www.meetscoresonline.com/R35397",
    #     "source": "file", "state": "IN",
    #     "start_date": "2025-12-12", "location": "Indianapolis, IN",
    # },
    # {
    #     "meet_id": "MSO-35120",
    #     "name": "2026 California Grand Invitational",
    #     "mso_url": "https://www.meetscoresonline.com/R35120",
    #     "source": "mso", "state": "CA",
    #     "start_date": "2026-01-09", "location": "Anaheim, CA",
    # },
    # {
    #     "meet_id": "MSO-35799",
    #     "name": "2026 Jaycie Phelps Midwest Showdown",
    #     "mso_url": "https://www.meetscoresonline.com/R35799",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-23", "location": "French Lick, IN",
    # },
    # {
    #     "meet_id": "MSO-35846",
    #     "name": "2026 Jaycie Phelps Midwest Showdown NGA",
    #     "mso_url": "https://www.meetscoresonline.com/R35846",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-23", "location": "French Lick, IN",
    # },
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
    # {
    #     "meet_id": "MSO-36190",
    #     "name": "2026 Flip For Your Cause [NGA]",
    #     "mso_url": "https://www.meetscoresonline.com/R36190",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-20", "location": "Westfield, IN",
    # },
    # {
    #     "meet_id": "MSO-36315",
    #     "name": "2026 Shamrock Shenanigans At Midwest",
    #     "mso_url": "https://www.meetscoresonline.com/R36315",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-02-27", "location": "Dyer, IN",
    # },
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
    #  {
    #     "meet_id": "MSO-36478",
    #     "name": "2026 IN Compulsory State Championships",
    #     "mso_url": "https://www.meetscoresonline.com/Results/36478",
    #     # "mso_url": "https://www.meetscoresonline.com/2026-IN-Compulsory-State-Championships",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-03-13", "location": "Crown Pointe, IN",
    # }
    # {
        "meet_id": "MSO-36489",
        "name": "2026 I AM Classic Meet",
        "mso_url": "https://www.meetscoresonline.com/R36489",
        "source": "mso", "state": "IN",
        "start_date": "2026-03-13", "location": "Plymouth, IN",
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
    # {
    #     "meet_id": "MSO-35610",
    #     "name": "2026 Wabash Valley Classic Meet NGA",
    #     "mso_url": "https://www.meetscoresonline.com/R35610",
    #     "source": "mso", "state": "IN",
    #     "start_date": "2026-01-09", "location": "Terre Haute, IN",
    # },
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
                existing.mso_url = m.get("mso_url") or existing.mso_url
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
                mso_url=m.get("mso_url"),
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
    Groups by level, division, and event, then ranks by score (higher = better).
    Only calculates placements for rows where place is None.
    
    Args:
        normalized_rows: List of normalized score dicts
        meet_id: Meet ID for logging
        
    Returns:
        List of normalized rows with place values calculated
    """
    # Check if any rows are missing place values
    missing_places = sum(1 for row in normalized_rows if row.get("place") is None)
    if missing_places == 0:
        return normalized_rows
    
    logger.info("Calculating placements for %d scores missing place data (meet: %s)", missing_places, meet_id)
    
    # Group by level, division, and event for ranking
    from collections import defaultdict
    groups = defaultdict(list)
    
    for idx, row in enumerate(normalized_rows):
        key = (
            row.get("level", ""),
            row.get("division", ""),
            row.get("event", "")
        )
        groups[key].append((idx, row))
    
    # Calculate ranks for each group
    for key, rows_with_idx in groups.items():
        level, division, event = key
        
        # Sort by score descending (higher score = better)
        sorted_rows = sorted(
            rows_with_idx,
            key=lambda x: (x[1].get("score") or 0),
            reverse=True
        )
        
        # Assign places (handle ties - same score = same place)
        # Place starts at 1, increments when score changes
        current_place = 1
        prev_score = None
        
        for rank_idx, (orig_idx, row) in enumerate(sorted_rows):
            score = row.get("score")
            
            # Only calculate if place is missing
            if row.get("place") is None:
                # If score is different from previous, update place to current rank position
                if prev_score is not None and score != prev_score:
                    current_place = rank_idx + 1
                elif rank_idx == 0:
                    # First row always gets place 1
                    current_place = 1
                
                normalized_rows[orig_idx]["place"] = current_place
                prev_score = score
    
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

        # Bulk check existing hashes (much faster than N queries).
        existing_hashes: set[str] = set()
        # De-dupe the IN list to keep the query small.
        unique_hashes = list(set(all_hashes))
        CHUNK = 900  # safe for most DB parameter limits
        for off in range(0, len(unique_hashes), CHUNK):
            chunk = unique_hashes[off : off + CHUNK]
            rows = db.query(Score.record_hash).filter(Score.record_hash.in_(chunk)).all()
            existing_hashes.update(r[0] for r in rows)

        # If everything already exists, short-circuit without gym/athlete lookups.
        if len(existing_hashes) == len(unique_hashes):
            return 0, skipped + len(all_hashes)

        # Track record_hashes we've seen in THIS batch to prevent duplicates within the same batch
        seen_hashes_in_batch: set[str] = set()

        for plan in planned:
            # If all events for this athlete row are already present, skip cheaply.
            if plan["hashes"] and all(h in existing_hashes for h in plan["hashes"]):
                skipped += len(plan["hashes"])
                continue

            gym = _get_or_create_gym(db, plan["gym_name"])
            athlete = _get_or_create_athlete(db, plan["athlete_name"], gym, plan["level"])
            if not athlete:
                skipped += len(plan["events"])
                continue

            session_obj = _get_or_create_session(
                db,
                meet_db_id=meet.id,
                session_key=plan.get("session_key") or "",
                session_number=plan.get("session_number"),
                start_time=plan.get("session_start_time"),
            )

            for (event_label, score_val, place), record_hash in zip(plan["events"], plan["hashes"]):
                if record_hash in seen_hashes_in_batch or record_hash in existing_hashes:
                    skipped += 1
                    continue
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

        # Step 0: Determine meets source
        if args.use_target_meets:
            print(f"  Mode: Using hardcoded TARGET_MEETS array")
            meets_to_process = TARGET_MEETS
            print(f"  Meets: {len(meets_to_process)} target meets (2025-26 season)")
        else:
            print(f"  Mode: Auto-discovery from MSO")
            print(f"  States: {', '.join(args.states)}")
            print(f"  Discovering meets...")
            discovered_meets = discover_meets(states=args.states)
            meets_to_process = discovered_meets
            print(f"  Discovered: {len(discovered_meets)} meets")

        print(f"{'='*60}\n")

        # Step 1: Upsert all meets
        print(f"[1/2] Saving meets to database...")
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
            meets_to_scrape = meets_to_process[: args.scrape_limit]
            print(f"[2/2] Scraping scores (limit: {args.scrape_limit} meets)...")

        if not args.meet and not args.interactive:
            print(f"[2/2] Scraping scores (limit: {args.scrape_limit} meets)...")
        else:
            print(f"[2/2] Scraping scores for {len(meets_to_scrape)} selected meet(s)...")

        score_rows_total = 0
        score_saved_total = 0

        for i, meet in enumerate(meets_to_scrape):
            mso_url = meet.get("mso_url")
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
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(user_agent=DEFAULT_UA)

                # Cheap change detection: fingerprint the rendered results page.
                fp = None
                try:
                    fp = fingerprint_mso_results_page_with_context(context, mso_url)
                except Exception:
                    fp = None

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
                                state.last_polled_at = now
                                db.commit()
                                print(f"      [{i+1}] {name} - no change detected, skipping")
                                continue

                            state.last_fingerprint = fp
                            state.last_polled_at = now
                            state.last_changed_at = now
                            db.commit()
                    finally:
                        db.close()

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
) -> tuple[int, int]:
    """
    Programmatic entrypoint for ingestion (Cloud Run jobs, other apps, tests).

    Returns (score_rows_total, score_saved_total).
    """

    class _Args:
        def __init__(self) -> None:
            self.scrape_limit = scrape_limit
            self.meet = meet_id
            self.use_target_meets = use_target_meets
            self.states = states or ["IN", "OH", "MI", "CA"]
            self.interactive = interactive

    return _run_ingest_core(_Args())


def main() -> None:
    global args
    args = parser.parse_args()
    _run_ingest_core(args)


if __name__ == "__main__":
    main()