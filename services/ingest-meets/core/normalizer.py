"""
Data Normalization Layer

Converts raw records from any source (ScoreCat, MSO, Website)
into a single unified schema.
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Map source-specific event name variants to canonical USAG names
EVENT_NAME_MAP = {
    "vault": "vault",
    "vt": "vault",
    "v": "vault",
    "bars": "uneven_bars",
    "uneven bars": "uneven_bars",
    "ub": "uneven_bars",
    "pb": "parallel_bars",
    "parallel bars": "parallel_bars",
    "beam": "balance_beam",
    "balance beam": "balance_beam",
    "bb": "balance_beam",
    "floor": "floor_exercise",
    "floor exercise": "floor_exercise",
    "fx": "floor_exercise",
    "fx.": "floor_exercise",
    "all around": "AA",
    "all-around": "AA",
    "aa": "AA",
    "total": "AA",
    "high bar": "high_bar",
    "hb": "high_bar",
    "pommel horse": "pommel_horse",
    "ph": "pommel_horse",
    "rings": "rings",
    "still rings": "rings",
    "sr": "rings",
}

# Canonical level name normalization
LEVEL_MAP = {
    "xcel gold": "xcel_gold",
    "xcel silver": "xcel_silver",
    "xcel bronze": "xcel_bronze",
    "xcel platinum": "xcel_platinum",
    "xcel diamond": "xcel_diamond",
    "level 1": "1",
    "level 2": "2",
    "level 3": "3",
    "level 4": "4",
    "level 5": "5",
    "level 6": "6",
    "level 7": "7",
    "level 8": "8",
    "level 9": "9",
    "level 10": "10",
}


def normalize_event(raw) -> str:
    """Normalize a raw event name to canonical form."""
    if not raw:
        return "aa"
    key = str(raw).strip().lower().rstrip(".")
    return EVENT_NAME_MAP.get(key, key)


def normalize_level(raw) -> str:
    """Normalize a level string to canonical form."""
    if not raw:
        return ""
    key = str(raw).strip().lower()
    return LEVEL_MAP.get(key, str(raw).strip())


def normalize_athlete_name(raw) -> str:
    """
    Normalize athlete name to 'Firstname Lastname' format.
    Handles:
      - 'Smith, Jane'  → 'Jane Smith'
      - 'JANE SMITH'   → 'Jane Smith'
      - 'Jane A. Smith' → 'Jane A. Smith' (kept as-is for resolver)
    """
    if not raw:
        return ""
    name = str(raw).strip()

    # Handle 'Last, First' format
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        name = f"{parts[1]} {parts[0]}"

    # Title case
    name = " ".join(w.capitalize() for w in name.split())
    return name


def normalize_gym_name(raw) -> str:
    """
    Normalize gym name for display/normalization purposes.
    
    NOTE: For database lookups, use core.gym_normalizer.normalize_gym_name()
    which includes canonical mapping to prevent duplicates.
    
    This function is kept for backward compatibility in normalizer.
    """
    if not raw:
        return ""
    return " ".join(str(raw).strip().split()).title()


def normalize_scorecat_record(raw: Dict) -> Dict:
    """
    Normalize a raw ScoreCat JSON record.
    ScoreCat field names vary; this handles common patterns.
    """
    athlete = normalize_athlete_name(
        raw.get("athleteName") or raw.get("athlete_name") or raw.get("name") or ""
    )
    gym = normalize_gym_name(
        raw.get("gymName") or raw.get("gym_name") or raw.get("gym") or raw.get("club") or ""
    )
    event = normalize_event(
        raw.get("event") or raw.get("eventName") or raw.get("apparatus") or ""
    )
    level = normalize_level(
        raw.get("level") or raw.get("division") or ""
    )
    score = _parse_score(raw.get("score") or raw.get("totalScore") or 0)
    meet_id = str(raw.get("meetId") or raw.get("meet_id") or "")
    session = raw.get("session") or raw.get("sessionNumber")

    return {
        "athlete_name": athlete,
        "gym": gym,
        "event": event,
        "level": level,
        "score": score,
        "meet_id": meet_id,
        "session": session,
        "source": "scorecat",
        "timestamp": datetime.utcnow().isoformat(),
    }


def normalize_mso_record(raw: Dict) -> List[Dict]:
    """
    Normalize a raw MSO HTML scraper record.
    The HTML scraper extracts individual event scores, so we expand into multiple records.
    Note: HTML scraper doesn't have placement data for individual events, only AA.
    """
    base = {
        "athlete_name": normalize_athlete_name(raw.get("athlete_name", "")),
        "gym": normalize_gym_name(raw.get("gym", "")),
        "level": normalize_level(raw.get("level", "")),
        "division": raw.get("division"),
        "meet_id": raw.get("meet_id", ""),
        "session": raw.get("session"),
        "source": raw.get("source", "mso"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    records = []
    
    # All-Around (has placement data from HTML scraper)
    aa_score = raw.get("score")
    if aa_score is not None:
        parsed_aa = _parse_score(aa_score)
        if parsed_aa is not None:
            records.append({
                **base,
                "event": "AA",
                "score": parsed_aa,
                "place": raw.get("place"),  # HTML scraper extracts AA place
            })
    
    # Individual events (with placement data from HTML scraper)
    event_map = [
        ("vault", "VT", "vault_place"),
        ("bars", "UB", "bars_place"),
        ("beam", "BB", "beam_place"),
        ("floor", "FX", "floor_place"),
    ]
    
    for score_key, event_code, place_key in event_map:
        score = raw.get(score_key)
        place = raw.get(place_key)
        if score is not None:
            if isinstance(score, (int, float)):
                if score >= 0.0:
                    records.append({
                        **base,
                        "event": event_code,
                        "score": float(score),
                        "place": place,  # Individual event placement from HTML scraper
                    })
            else:
                parsed_score = _parse_score(score)
                if parsed_score is not None and parsed_score >= 0.0:
                    records.append({
                        **base,
                        "event": event_code,
                        "score": parsed_score,
                        "place": place,  # Individual event placement from HTML scraper
                    })
    
    # Debug: log expansion for first athlete with place values
    if not hasattr(normalize_mso_record, '_debug_logged'):
        logger.info("Normalizer expanded first athlete into %d records: %s", 
                   len(records), [(r.get('event'), r.get('score'), f"place={r.get('place')}") for r in records])
        # Log place values from raw data
        logger.info("Raw place values: AA=%s, vault=%s, bars=%s, beam=%s, floor=%s",
                   raw.get('place'), raw.get('vault_place'), raw.get('bars_place'), 
                   raw.get('beam_place'), raw.get('floor_place'))
        normalize_mso_record._debug_logged = True
    
    # Return list of records (at least AA if available)
    return records if records else []


def normalize_mso_api_record(raw: Dict) -> List[Dict]:
    """
    Normalize a raw MSO API record.
    The API returns one row per athlete with all events, so we need to
    expand it into multiple records (one per event).
    """
    base = {
        "athlete_name": normalize_athlete_name(raw.get("athlete_name", "")),
        "gym": normalize_gym_name(raw.get("gym", "")),
        "level": normalize_level(raw.get("level", "")),
        "division": raw.get("division"),
        "meet_id": raw.get("meet_id", ""),
        "session": raw.get("session"),
        "source": "mso_api",
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Create records for each event that has a score
    records = []
    
    # All-Around
    aa_score = raw.get("aa_score")
    if aa_score is not None and aa_score != "":
        parsed_aa = _parse_score(aa_score)
        if parsed_aa is not None:
            records.append({
                **base,
                "event": "AA",
                "score": parsed_aa,
                "place": raw.get("aa_place"),
            })
    
    # Individual events
    event_map = [
        ("vault", "VT", "vault_place"),
        ("bars", "UB", "bars_place"),
        ("beam", "BB", "beam_place"),
        ("floor", "FX", "floor_place"),
    ]
    
    for score_key, event_code, place_key in event_map:
        score = raw.get(score_key)
        # The API scraper already parsed floats, so score might be a float or None
        # Check if we have a valid numeric score
        if score is not None:
            # If it's already a float/int, use it directly
            if isinstance(score, (int, float)):
                # Valid score (gymnastics scores are typically 0.0 to 10.0)
                if score >= 0.0:
                    records.append({
                        **base,
                        "event": event_code,
                        "score": float(score),
                        "place": raw.get(place_key),
                    })
            else:
                # Try parsing if it's a string
                parsed_score = _parse_score(score)
                if parsed_score is not None and parsed_score >= 0.0:
                    records.append({
                        **base,
                        "event": event_code,
                        "score": parsed_score,
                        "place": raw.get(place_key),
                    })
    
    # Debug: log place values for first athlete from API
    if not hasattr(normalize_mso_api_record, '_debug_logged'):
        logger.info("API Normalizer place values for first athlete: AA=%s, vault=%s, bars=%s, beam=%s, floor=%s",
                   raw.get('aa_place'), raw.get('vault_place'), raw.get('bars_place'), 
                   raw.get('beam_place'), raw.get('floor_place'))
        logger.info("API Normalizer expanded first athlete into %d records: %s", 
                   len(records), [(r.get('event'), r.get('score'), f"place={r.get('place')}") for r in records])
        normalize_mso_api_record._debug_logged = True
    
    # Return empty list if no records (shouldn't happen, but handle gracefully)
    if not records:
        logger.warning("No events found for athlete %s at meet %s", base.get("athlete_name"), base.get("meet_id"))
    
    return records


def normalize_website_record(raw: Dict) -> Dict:
    """Normalize a raw website parser record."""
    return {
        "athlete_name": normalize_athlete_name(raw.get("athlete_name", "")),
        "gym": normalize_gym_name(raw.get("gym", "")),
        "event": normalize_event(raw.get("event", "AA")),
        "level": normalize_level(raw.get("level", "")),
        "score": _parse_score(raw.get("score")),
        "place": raw.get("place"),
        "meet_id": raw.get("meet_id", ""),
        "session": raw.get("session"),
        "source": raw.get("source", "website"),
        "timestamp": datetime.utcnow().isoformat(),
    }


def _parse_score(value) -> Optional[float]:
    """Safely parse score to float."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+\.\d+)", str(value))
    return float(match.group(1)) if match else None
