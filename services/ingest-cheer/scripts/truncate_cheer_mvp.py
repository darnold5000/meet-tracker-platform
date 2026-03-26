#!/usr/bin/env python3
"""
Delete every row in ``cheer_mvp_*`` tables (schema stays). Uses FK-safe DELETE order.

From ``services/ingest-cheer`` with ``DATABASE_URL`` set:

  python scripts/truncate_cheer_mvp.py

Then re-run Varsity ingest / seed as needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from db.database import SessionLocal, create_tables


def truncate_cheer_mvp_tables() -> None:
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM cheer_mvp_performances"))
        db.execute(text("DELETE FROM cheer_mvp_sessions"))
        db.execute(text("DELETE FROM cheer_mvp_meets"))
        db.execute(text("DELETE FROM cheer_mvp_teams"))
        db.commit()
    finally:
        db.close()


def main() -> int:
    create_tables()
    truncate_cheer_mvp_tables()
    print("Truncated cheer_mvp_performances, sessions, meets, teams (tables kept).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
