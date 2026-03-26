"""
Hardcoded Varsity TV events for cheer ingest (parallel idea to ``TARGET_MEETS`` for MSO).

Edit ``CHEER_TARGET_VAR_EVENTS`` to list competitions you always want considered when
``cheer_ingest_main`` runs (merged with DB ``VARSITY-*`` meets active today).

Each entry:
  - ``event_id`` (int): Varsity numeric id from the URL ``/events/<id>-...``
  - ``name`` (optional str): display name for ``CheerMvpMeet`` when not in DB yet
  - ``start_date`` / ``end_date`` (optional ``datetime.date``): inclusive window in
    ``CHEER_INGEST_TZ``'s calendar. If **both omitted**, the event is synced **every**
    run (remove it from the list when you no longer want polling).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, TypedDict

from agents.varsity_client import cheer_mvp_meet_covers_calendar_day

# Typed row for documentation / editors; runtime uses plain dicts.
class CheerTargetVarEvent(TypedDict, total=False):
    event_id: int
    name: str
    start_date: date
    end_date: date


CHEER_TARGET_VAR_EVENTS: List[Dict[str, Any]] = [
    {
        "event_id": 14478875,
        "name": "2026 CHEERSPORT National All Star Cheerleading Championship",
        # Feb 13–15, 2026 (Atlanta / GWCC); adjust if Varsity updates dates.
        "start_date": date(2026, 2, 13),
        "end_date": date(2026, 2, 15),
    },
]


def target_var_event_active_on_day(entry: Dict[str, Any], on_day: date) -> bool:
    """Whether this target row should run on ``on_day`` (in ingest timezone)."""
    start = entry.get("start_date")
    end = entry.get("end_date")
    if start is None and end is None:
        return True
    return cheer_mvp_meet_covers_calendar_day(
        start, end, on_day, include_undated=False
    )
