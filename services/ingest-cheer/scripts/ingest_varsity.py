#!/usr/bin/env python3
"""
Pull Varsity TV schedule, results index, and rankings metadata into stdout or Cheer MVP meets.

Examples:
  python scripts/ingest_varsity.py --schedule
  python scripts/ingest_varsity.py --results --results-limit 40
  python scripts/ingest_varsity.py --rankings
  python scripts/ingest_varsity.py --ranking-table 6811625 36950
  python scripts/ingest_varsity.py --sync-meets
  python scripts/ingest_varsity.py --upcoming
  python scripts/ingest_varsity.py --event-results 14479023
  python scripts/ingest_varsity.py --event-results 14479023 --event-results-sync-db \\
      --event-name "2026 Athletic Championships Atlanta Nationals"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _row_json(row: dict) -> dict:
    """JSON-serialize datetimes in event rows."""
    out = dict(row)
    for k in ("start_at", "end_at"):
        v = out.get(k)
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def cmd_schedule(_args: argparse.Namespace) -> int:
    from agents.varsity_client import fetch_schedule_events

    rows = fetch_schedule_events()
    for row in rows:
        print(json.dumps(_row_json(row), ensure_ascii=False))
    if rows:
        print(
            "Note: --schedule only prints JSON. To upsert into cheer_mvp_meets, run --sync-meets (DATABASE_URL).",
            file=sys.stderr,
        )
    return 0


def cmd_upcoming(args: argparse.Namespace) -> int:
    from agents.varsity_client import top_upcoming_schedule_events_from_ticker

    for row in top_upcoming_schedule_events_from_ticker(
        limit=args.upcoming_limit, exclude_rebroadcast=True
    ):
        print(json.dumps(_row_json(row), ensure_ascii=False))
    print(
        "Note: --upcoming only prints JSON. To upsert meets into Postgres (cheer_mvp_meets), "
        "set DATABASE_URL and run: python scripts/ingest_varsity.py --sync-meets",
        file=sys.stderr,
    )
    return 0


def cmd_results(args: argparse.Namespace) -> int:
    from agents.varsity_client import iter_results_events

    n = 0
    for row in iter_results_events():
        print(json.dumps(_row_json(row), ensure_ascii=False))
        n += 1
        if args.results_limit and n >= args.results_limit:
            break
    return 0


def cmd_rankings(_args: argparse.Namespace) -> int:
    from agents.varsity_client import fetch_ranking_hub_cards

    for card in fetch_ranking_hub_cards():
        print(json.dumps(card, ensure_ascii=False))
    return 0


def cmd_ranking_table(args: argparse.Namespace) -> int:
    from agents.varsity_client import (
        fetch_ranking_layout,
        fetch_ranking_table_rows,
        iter_ranking_table_urls,
    )

    rid = int(args.ranking_id)
    layout = fetch_ranking_layout(rid)
    want_section = int(args.section_id) if args.section_id is not None else None
    for spec in iter_ranking_table_urls(rid, layout):
        sid = spec.get("section_id")
        if want_section is not None and sid != want_section:
            continue
        print(json.dumps(spec, ensure_ascii=False))
        rows = fetch_ranking_table_rows(spec["table_html_url"])
        for cells in rows[: args.table_preview_rows]:
            print(json.dumps(cells, ensure_ascii=False))
    return 0


def cmd_event_results(args: argparse.Namespace) -> int:
    from agents.varsity_client import iter_event_hub_result_rows

    eid = int(args.event_results)
    facets = args.event_facets
    n = 0
    for row in iter_event_hub_result_rows(eid, page_size=args.event_page_size, facets=facets):
        print(json.dumps(row, ensure_ascii=False))
        n += 1
    if n == 0:
        print(json.dumps({"warning": "no_rows", "event_id": eid}, indent=2), file=sys.stderr)
    return 0


def cmd_event_results_sync_db(args: argparse.Namespace) -> int:
    from agents.varsity_client import sync_event_results_to_cheer_mvp
    from db.database import SessionLocal, create_tables

    create_tables()
    db = SessionLocal()
    try:
        stats = sync_event_results_to_cheer_mvp(
            db,
            int(args.event_results),
            meet_name=args.event_name,
            page_size=args.event_page_size,
            facets=args.event_facets,
        )
    finally:
        db.close()
    print(json.dumps(stats, indent=2))
    return 0 if "error" not in stats else 1


def cmd_sync_meets(args: argparse.Namespace) -> int:
    from agents.varsity_client import sync_cheer_mvp_meets_from_varsity
    from db.database import SessionLocal, create_tables

    create_tables()
    limit = args.results_limit
    if limit is None:
        raw = os.getenv("VARSITY_RESULTS_MAX_ITEMS", "200").strip()
        limit = int(raw) if raw.isdigit() else 200

    db = SessionLocal()
    try:
        stats = sync_cheer_mvp_meets_from_varsity(db, results_max_items=limit)
    finally:
        db.close()

    print(json.dumps(stats, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Varsity TV ingest (schedule, results, rankings)")
    p.add_argument(
        "--schedule",
        action="store_true",
        help="Print all event-ticker events to stdout (no DB). Use --sync-meets to persist.",
    )
    p.add_argument(
        "--upcoming",
        action="store_true",
        help="Print next N ticker events to stdout only (no DB). Use --sync-meets to persist meets.",
    )
    p.add_argument(
        "--upcoming-limit",
        type=int,
        default=3,
        help="Row count for --upcoming (default 3)",
    )
    p.add_argument("--results", action="store_true", help="Print paginated results index (JSON lines)")
    p.add_argument(
        "--results-limit",
        type=int,
        default=None,
        help="Cap results index rows for --results (unlimited if omitted). "
        "For --sync-meets, defaults to env VARSITY_RESULTS_MAX_ITEMS or 200 when omitted.",
    )
    p.add_argument("--rankings", action="store_true", help="Print rankings hub cards")
    p.add_argument(
        "--ranking-table",
        nargs="+",
        metavar="ID",
        help="Ranking document id, optional section id (Flo section id); prints table specs + row preview",
    )
    p.add_argument(
        "--table-preview-rows",
        type=int,
        default=25,
        help="Max data rows to print for --ranking-table",
    )
    p.add_argument(
        "--sync-meets",
        action="store_true",
        help="Upsert CheerMvpMeet from schedule + results (meet_key VARSITY-<event_id>)",
    )
    p.add_argument(
        "--event-results",
        metavar="EVENT_ID",
        help="Print all score rows for one Varsity event (tv.varsity.com event id from URL)",
    )
    p.add_argument(
        "--event-results-sync-db",
        action="store_true",
        help="With --event-results: load results into cheer_mvp_* (replaces sessions/performances for that meet)",
    )
    p.add_argument(
        "--event-name",
        default=None,
        help="Display name for CheerMvpMeet when using --event-results-sync-db",
    )
    p.add_argument(
        "--event-page-size",
        type=int,
        default=100,
        help="Page size for event-hub /results API (default 100)",
    )
    p.add_argument(
        "--event-facets",
        default=None,
        help='Optional facets JSON string, e.g. \'{"class":"Cheer","category":"Level 1"}\'',
    )

    args = p.parse_args()
    if not (
        args.schedule
        or args.upcoming
        or args.results
        or args.rankings
        or args.ranking_table
        or args.sync_meets
        or args.event_results
    ):
        p.print_help()
        return 2

    if args.schedule:
        return cmd_schedule(args)
    if args.upcoming:
        return cmd_upcoming(args)
    if args.results:
        return cmd_results(args)
    if args.rankings:
        return cmd_rankings(args)
    if args.ranking_table:
        args.ranking_id = args.ranking_table[0]
        args.section_id = args.ranking_table[1] if len(args.ranking_table) > 1 else None
        return cmd_ranking_table(args)
    if args.sync_meets:
        return cmd_sync_meets(args)
    if args.event_results:
        if args.event_results_sync_db:
            return cmd_event_results_sync_db(args)
        return cmd_event_results(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
