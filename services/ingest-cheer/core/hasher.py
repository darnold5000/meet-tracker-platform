"""
Hash-based deduplication for inbound score records.

Prevents storing duplicate records when live feeds resend unchanged data
or when multiple scrapers overlap on the same meet.
"""

import hashlib
import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# In-memory seen-set for a single process run.
# In production, back this with Redis SET or a DB column.
_seen_hashes: set = set()


def compute_hash(record: Dict) -> str:
    """
    Compute a stable SHA-256 hash for a normalized score record.
    Uses the fields that uniquely identify a result.
    """
    key = {
        "athlete_name": (record.get("athlete_name") or "").lower().strip(),
        "gym": (record.get("gym") or "").lower().strip(),
        "meet_id": str(record.get("meet_id") or ""),
        "event": str(record.get("event") or ""),
        "score": str(record.get("score") or ""),
        "level": str(record.get("level") or ""),
        "session": str(record.get("session") or ""),
    }
    serialized = json.dumps(key, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def is_duplicate(record: Dict) -> bool:
    """Return True if this record has already been seen."""
    h = compute_hash(record)
    return h in _seen_hashes


def mark_seen(record: Dict) -> str:
    """Mark a record as seen and return its hash."""
    h = compute_hash(record)
    _seen_hashes.add(h)
    return h


def reset() -> None:
    """Clear the seen-set (useful for testing)."""
    _seen_hashes.clear()


def seen_count() -> int:
    return len(_seen_hashes)
