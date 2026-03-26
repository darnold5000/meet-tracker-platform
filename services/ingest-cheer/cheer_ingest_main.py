#!/usr/bin/env python3
"""
Cheer-only Cloud Run / cron entrypoint: Varsity TV scores → cheer_mvp_*.

Does **not** run MSO, Playwright gymnastics ingest, or ``ingest.py``.

Merges two sources (unless ``CHEER_VAR_EVENT_IDS`` / ``--event-id`` override):

1. ``cheer_mvp_meets`` rows with ``meet_key`` ``VARSITY-<event_id>`` whose dates include **today**
   (see ``CHEER_INGEST_TZ``).
2. ``core/cheer_target_meets.CHEER_TARGET_VAR_EVENTS`` — same date rules; entries with **no**
   dates sync on **every** run (remove from the list when done).

Then pulls the event-hub **results** API and replaces sessions + performances per event.

Varsity does not expose a separate “mat order” feed: the same **results** payload is
where scored divisions appear; the site’s **event ticker** is broadcast scheduling, not
in-meet rotation.

Env:
  CHEER_INGEST_TZ           IANA zone for “today” (default America/New_York)
  CHEER_VAR_EVENT_IDS       Optional comma-separated event ids to sync **regardless of date**
  CHEER_VAR_SYNC_UNDATED_MEETS  If true, also sync VARSITY meets with no start/end dates
  CHEER_USE_CODE_TARGET_LIST    If ``0``/``false``, skip ``CHEER_TARGET_VAR_EVENTS`` (DB only)
  DATABASE_URL              Required (Postgres)

Optional one-off (from ``services/ingest-cheer``):
  python cheer_ingest_main.py --event-id 14479023
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("cheer_ingest_main")


def _today_in_tz(tz_name: str):
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(tz_name)).date()


def _meet_name_from_code_targets(event_id: int) -> Optional[str]:
    """Display name from ``CHEER_TARGET_VAR_EVENTS`` when configured."""
    from core.cheer_target_meets import CHEER_TARGET_VAR_EVENTS

    for entry in CHEER_TARGET_VAR_EVENTS:
        if entry.get("event_id") == event_id:
            n = entry.get("name")
            if isinstance(n, str) and n.strip():
                return n.strip()
    return None


def _event_ids_from_env() -> List[int]:
    raw = os.getenv("CHEER_VAR_EVENT_IDS", "").strip()
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def run_sync(
    *,
    force_event_ids: Optional[List[int]] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    from db.database import SessionLocal, create_tables
    from db.mvp_models import CheerMvpMeet
    from agents.varsity_client import (
        cheer_mvp_meet_covers_calendar_day,
        parse_varsity_event_id_from_meet_key,
        sync_event_results_to_cheer_mvp,
    )

    create_tables()
    tz = os.getenv("CHEER_INGEST_TZ", "America/New_York").strip() or "America/New_York"
    today = _today_in_tz(tz)
    undated = os.getenv("CHEER_VAR_SYNC_UNDATED_MEETS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    env_ids = _event_ids_from_env()
    if force_event_ids:
        target_ids = list(dict.fromkeys(force_event_ids))
    elif env_ids:
        target_ids = env_ids
        logger.info("CHEER_VAR_EVENT_IDS set; syncing %s (ignoring calendar filter)", target_ids)
    else:
        target_ids = []

    db = SessionLocal()
    results: List[Dict[str, Any]] = []
    try:
        if target_ids:
            for eid in target_ids:
                meet_name = _meet_name_from_code_targets(eid)
                if meet_name is None:
                    mk = f"VARSITY-{eid}"
                    m = db.query(CheerMvpMeet).filter(CheerMvpMeet.meet_key == mk).first()
                    if m and m.name:
                        meet_name = m.name
                logger.info("Sync Varsity event %s (meet_name=%s)", eid, meet_name)
                stats = sync_event_results_to_cheer_mvp(
                    db, eid, meet_name=meet_name, page_size=page_size
                )
                results.append(stats)
        else:
            to_sync: Dict[int, Optional[str]] = {}

            meets = db.query(CheerMvpMeet).all()
            for m in meets:
                eid = parse_varsity_event_id_from_meet_key(m.meet_key)
                if eid is None:
                    continue
                if not cheer_mvp_meet_covers_calendar_day(
                    m.start_date,
                    m.end_date,
                    today,
                    include_undated=undated,
                ):
                    logger.debug(
                        "Skip %s (event %s): %s..%s not covering %s",
                        m.meet_key,
                        eid,
                        m.start_date,
                        m.end_date,
                        today,
                    )
                    continue
                to_sync[eid] = m.name

            use_code_targets = os.getenv(
                "CHEER_USE_CODE_TARGET_LIST", "1"
            ).strip().lower() not in ("0", "false", "no", "off")
            if use_code_targets:
                from core.cheer_target_meets import (
                    CHEER_TARGET_VAR_EVENTS,
                    target_var_event_active_on_day,
                )

                for entry in CHEER_TARGET_VAR_EVENTS:
                    eid = entry.get("event_id")
                    if not isinstance(eid, int):
                        logger.warning("Skip invalid CHEER_TARGET_VAR_EVENTS row: %s", entry)
                        continue
                    if not target_var_event_active_on_day(entry, today):
                        continue
                    name = entry.get("name")
                    if eid not in to_sync:
                        to_sync[eid] = name if isinstance(name, str) else None
                    elif not to_sync[eid] and isinstance(name, str):
                        to_sync[eid] = name

            for eid, meet_name in sorted(to_sync.items()):
                label = meet_name or "(no name)"
                logger.info(
                    "Sync Varsity event %s (%s) — %s (%s)",
                    eid,
                    label,
                    today,
                    tz,
                )
                stats = sync_event_results_to_cheer_mvp(
                    db, eid, meet_name=meet_name, page_size=page_size
                )
                results.append(stats)

        if not results:
            logger.info(
                "No Varsity meets to sync (today=%s %s). "
                "Add ``core/cheer_target_meets.py`` entries, seed DB, "
                "or set CHEER_VAR_EVENT_IDS / use --event-id.",
                today,
                tz,
            )
    finally:
        db.close()

    summary = {
        "today": str(today),
        "timezone": tz,
        "synced": results,
        "count": len(results),
    }
    logger.info("Done: %s", json.dumps(summary, default=str))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Cheer Varsity score sync (no MSO)")
    p.add_argument(
        "--event-id",
        type=int,
        action="append",
        dest="event_ids",
        help="Sync this Varsity event id once (ignores date filter); repeat flag for multiple",
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="event-hub /results page size (default 100)",
    )
    args = p.parse_args()

    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL is not set")
        return 1

    try:
        run_sync(force_event_ids=args.event_ids, page_size=args.page_size)
    except Exception as exc:
        logger.exception("Cheer ingest failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
