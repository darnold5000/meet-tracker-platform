#!/usr/bin/env python3
"""Create cheer MVP demo data: two competitions (Atlanta + Chicago), teams, sessions, performances."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

# Repo: services/ingest-cheer
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.database import SessionLocal, create_tables
from db.mvp_models import CheerMvpMeet, CheerMvpPerformance, CheerMvpSession, CheerMvpTeam

MEET_KEY_ATL = "DEMO-ATL-2026"
MEET_KEY_CHI = "DEMO-CHI-2026"


def clear_mvp_tables(db: Session) -> None:
    db.execute(text("DELETE FROM cheer_mvp_performances"))
    db.execute(text("DELETE FROM cheer_mvp_sessions"))
    db.execute(text("DELETE FROM cheer_mvp_meets"))
    db.execute(text("DELETE FROM cheer_mvp_teams"))
    db.commit()


def seed_atlanta(db: Session) -> None:
    t_twisters = CheerMvpTeam(
        name="Tiny Twisters",
        gym_name="C4 Longhorns",
        level="L1 Tiny",
        division="Novice",
        normalized_division="L1 Tiny Novice",
    )
    t_cao = CheerMvpTeam(
        name="CAO Elite",
        gym_name="Cheer Atlanta",
        level="L1 Tiny",
        division="Novice",
        normalized_division="L1 Tiny Novice",
    )
    t_tek = CheerMvpTeam(
        name="T.E.K Cheer",
        gym_name="TEK Allstars",
        level="L1 Tiny",
        division="Novice",
        normalized_division="L1 Tiny Novice",
    )
    t_jpac = CheerMvpTeam(
        name="JPAC Level 7",
        gym_name="JPAC",
        level="L7",
        division="Large Coed",
        normalized_division="L7 Large Coed",
    )
    db.add_all([t_twisters, t_cao, t_tek, t_jpac])
    db.flush()

    meet = CheerMvpMeet(
        meet_key=MEET_KEY_ATL,
        name="Atlanta Nationals (demo)",
        location="Atlanta, GA",
        start_date=date(2026, 3, 20),
        end_date=date(2026, 3, 22),
        source="demo_seed",
    )
    db.add(meet)
    db.flush()

    s_morning = CheerMvpSession(meet_id=meet.id, name="Morning - L1 Tiny", display_order=0, start_time=None)
    s_afternoon = CheerMvpSession(meet_id=meet.id, name="Afternoon - L7", display_order=1, start_time=None)
    db.add_all([s_morning, s_afternoon])
    db.flush()

    base = datetime(2026, 3, 21, 8, 0, 0)
    perfs: list[CheerMvpPerformance] = [
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_morning.id,
            team_id=t_twisters.id,
            is_break=False,
            scheduled_time=base,
            status="live",
            display_order=0,
            round="Finals",
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_morning.id,
            team_id=t_cao.id,
            is_break=False,
            scheduled_time=datetime(2026, 3, 21, 8, 3, 0),
            status="upcoming",
            display_order=1,
            round="Finals",
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_morning.id,
            team_id=None,
            is_break=True,
            break_label="Break",
            scheduled_time=datetime(2026, 3, 21, 8, 6, 0),
            status="upcoming",
            display_order=2,
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_morning.id,
            team_id=t_tek.id,
            is_break=False,
            scheduled_time=datetime(2026, 3, 21, 8, 9, 0),
            status="upcoming",
            display_order=3,
            round="Finals",
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_afternoon.id,
            team_id=t_jpac.id,
            is_break=False,
            scheduled_time=datetime(2026, 3, 21, 14, 0, 0),
            actual_time=datetime(2026, 3, 21, 14, 2, 0),
            status="completed",
            display_order=0,
            round="Finals",
            final_score=88.16,
            rank=1,
            deductions=0.15,
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_afternoon.id,
            team_id=t_cao.id,
            is_break=False,
            scheduled_time=datetime(2026, 3, 21, 14, 10, 0),
            actual_time=datetime(2026, 3, 21, 14, 12, 0),
            status="completed",
            display_order=1,
            round="Finals",
            final_score=87.80,
            rank=2,
            deductions=0.30,
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_afternoon.id,
            team_id=t_tek.id,
            is_break=False,
            scheduled_time=datetime(2026, 3, 21, 14, 20, 0),
            actual_time=datetime(2026, 3, 21, 14, 22, 0),
            status="completed",
            display_order=2,
            round="Finals",
            final_score=86.90,
            rank=3,
            deductions=0.20,
        ),
    ]
    db.add_all(perfs)


def seed_chicago(db: Session) -> None:
    t_fire = CheerMvpTeam(
        name="Firestorm Youth",
        gym_name="Illinois Heat",
        level="Youth 2",
        division="Small",
        normalized_division="Youth 2 Small",
    )
    t_gle = CheerMvpTeam(
        name="Great Lakes Elite",
        gym_name="GLE Cheer",
        level="Youth 2",
        division="Small",
        normalized_division="Youth 2 Small",
    )
    t_windy = CheerMvpTeam(
        name="Windy City Stars",
        gym_name="Chicago Premier",
        level="Senior 5",
        division="Large Coed",
        normalized_division="Senior 5 Large Coed",
    )
    db.add_all([t_fire, t_gle, t_windy])
    db.flush()

    meet = CheerMvpMeet(
        meet_key=MEET_KEY_CHI,
        name="Windy City Classic (demo)",
        location="Chicago, IL",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 12),
        source="demo_seed",
    )
    db.add(meet)
    db.flush()

    s_day1 = CheerMvpSession(meet_id=meet.id, name="Day 1 - Youth 2", display_order=0, start_time=None)
    s_day2 = CheerMvpSession(meet_id=meet.id, name="Day 2 - Senior 5", display_order=1, start_time=None)
    db.add_all([s_day1, s_day2])
    db.flush()

    perfs: list[CheerMvpPerformance] = [
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day1.id,
            team_id=t_fire.id,
            is_break=False,
            scheduled_time=datetime(2026, 4, 11, 9, 0, 0),
            status="upcoming",
            display_order=0,
            round="Prelims",
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day1.id,
            team_id=t_gle.id,
            is_break=False,
            scheduled_time=datetime(2026, 4, 11, 9, 15, 0),
            status="live",
            display_order=1,
            round="Prelims",
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day1.id,
            team_id=None,
            is_break=True,
            break_label="Warm-up block",
            scheduled_time=datetime(2026, 4, 11, 9, 30, 0),
            status="upcoming",
            display_order=2,
        ),
        # Scored finals on day 2
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day2.id,
            team_id=t_windy.id,
            is_break=False,
            scheduled_time=datetime(2026, 4, 12, 15, 0, 0),
            actual_time=datetime(2026, 4, 12, 15, 4, 0),
            status="completed",
            display_order=0,
            round="Finals",
            final_score=91.42,
            rank=1,
            deductions=0.10,
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day2.id,
            team_id=t_gle.id,
            is_break=False,
            scheduled_time=datetime(2026, 4, 12, 15, 12, 0),
            actual_time=datetime(2026, 4, 12, 15, 14, 0),
            status="completed",
            display_order=1,
            round="Finals",
            final_score=90.05,
            rank=2,
            deductions=0.25,
        ),
        CheerMvpPerformance(
            meet_id=meet.id,
            session_id=s_day2.id,
            team_id=t_fire.id,
            is_break=False,
            scheduled_time=datetime(2026, 4, 12, 15, 24, 0),
            actual_time=datetime(2026, 4, 12, 15, 26, 0),
            status="completed",
            display_order=2,
            round="Finals",
            final_score=89.88,
            rank=3,
            deductions=0.18,
        ),
    ]
    db.add_all(perfs)


def main() -> int:
    create_tables()
    db = SessionLocal()
    try:
        clear_mvp_tables(db)
        seed_atlanta(db)
        seed_chicago(db)
        db.commit()
        print(f"Seeded cheer MVP: {MEET_KEY_ATL} (Atlanta), {MEET_KEY_CHI} (Chicago)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
