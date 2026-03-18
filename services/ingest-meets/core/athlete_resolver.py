"""
Athlete Identity Resolution

The hardest problem: the same athlete appears under different name formats
across meets and sources. This module builds a canonical identity graph
using fuzzy string matching + gym + level cross-referencing.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

FUZZY_MATCH_THRESHOLD = 88  # Score out of 100 — tunable
GYM_BONUS = 10              # Add to score if gym also matches


class AthleteResolver:
    """
    In-memory athlete resolver for a processing session.
    For production use, wire this to the DB layer.
    """

    def __init__(self):
        # List of known canonical athletes
        # Each entry: {"id": str, "name": str, "gym": str, "level": str}
        self._athletes: List[Dict] = []

    def resolve(self, raw_name: str, gym: str = "", level: str = "") -> Tuple[Optional[str], bool]:
        """
        Resolve a raw name to a canonical athlete id.

        Args:
            raw_name: Name as it appeared in the source
            gym: Gym name for cross-reference
            level: Level for cross-reference

        Returns:
            (athlete_id, is_new) — is_new=True if a new athlete was created
        """
        normalized_name = _normalize_for_matching(raw_name)
        normalized_gym = _normalize_for_matching(gym)

        best_id, best_score = self._find_best_match(normalized_name, normalized_gym, level)

        if best_score >= FUZZY_MATCH_THRESHOLD:
            logger.debug(
                "Resolved '%s' → athlete_id=%s (score=%d)", raw_name, best_id, best_score
            )
            return best_id, False

        # No match — create new canonical entry
        new_id = self._create_athlete(raw_name, gym, level)
        logger.info("New athlete: '%s' | gym=%s | level=%s → id=%s", raw_name, gym, level, new_id)
        return new_id, True

    def _find_best_match(self, name: str, gym: str, level: str) -> Tuple[Optional[str], int]:
        if not self._athletes:
            return None, 0

        candidates = [a["_normalized_name"] for a in self._athletes]
        matches = process.extractOne(name, candidates, scorer=fuzz.token_sort_ratio)

        if not matches:
            return None, 0

        best_name, base_score, best_idx = matches
        matched_athlete = self._athletes[best_idx]

        # Boost score if gym also matches
        gym_score = fuzz.token_sort_ratio(gym, matched_athlete.get("_normalized_gym", ""))
        if gym_score > 80:
            base_score = min(100, base_score + GYM_BONUS)

        return matched_athlete["id"], base_score

    def _create_athlete(self, raw_name: str, gym: str, level: str) -> str:
        canonical_name = _to_canonical_name(raw_name)
        new_id = f"athlete_{len(self._athletes) + 1:05d}"
        self._athletes.append({
            "id": new_id,
            "name": canonical_name,
            "gym": gym,
            "level": level,
            "_normalized_name": _normalize_for_matching(canonical_name),
            "_normalized_gym": _normalize_for_matching(gym),
        })
        return new_id

    def athlete_count(self) -> int:
        return len(self._athletes)


def _normalize_for_matching(text: str) -> str:
    """Lowercase, strip punctuation, normalize whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _to_canonical_name(raw: str) -> str:
    """
    Convert any name format to 'Firstname Lastname'.
    Handles:
      - 'Smith, Jane'
      - 'jane smith'
      - 'SMITH JANE A'
    """
    raw = raw.strip()
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        raw = f"{parts[1]} {parts[0]}"
    return " ".join(w.capitalize() for w in raw.split())


def compare_names(name1: str, name2: str) -> int:
    """Utility: return fuzzy similarity score between two names (0-100)."""
    n1 = _normalize_for_matching(name1)
    n2 = _normalize_for_matching(name2)
    return fuzz.token_sort_ratio(n1, n2)
