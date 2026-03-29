"""Cheer MVP JSON API: search, meet timeline, results."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from cheer_scores.db import fetch_all, fetch_one

router = APIRouter(prefix="/api/mvp", tags=["mvp"])

# Team routine with at least one numeric score posted (excludes schedule-only / placeholder rows).
_MVP_SCORED_PERF_ON = """
  p.meet_id = m.id
  AND p.is_break = false
  AND p.team_id IS NOT NULL
  AND (
    p.final_score IS NOT NULL
    OR p.raw_score IS NOT NULL
    OR p.performance_score IS NOT NULL
  )
"""

_MVP_SCORED_PERF_ON_TEAM = """
  p.team_id = t.id
  AND p.is_break = false
  AND p.team_id IS NOT NULL
  AND (
    p.final_score IS NOT NULL
    OR p.raw_score IS NOT NULL
    OR p.performance_score IS NOT NULL
  )
"""

_MVP_MEET_HAS_SCORES_SQL = """
EXISTS (
  SELECT 1 FROM cheer_mvp_performances p
  WHERE p.meet_id = m.id
    AND p.is_break = false
    AND p.team_id IS NOT NULL
    AND (
      p.final_score IS NOT NULL
      OR p.raw_score IS NOT NULL
      OR p.performance_score IS NOT NULL
    )
)
"""


def _json_val(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_val(v) for k, v in r.items()}


@router.get("/search")
def mvp_search(
    q: str = Query("", min_length=0, max_length=200),
    gym: str = Query(
        "",
        max_length=255,
        description="If set, only meets that have at least one scored routine for this gym name (case-insensitive exact match on trimmed gym_name).",
    ),
):
    try:
        needle = f"%{q.strip().lower()}%"
        gym_trim = gym.strip()
        gym_names: list[str] = []

        if not q.strip():
            teams = fetch_all(
                """
                SELECT id, name, gym_name, level, division
                FROM cheer_mvp_teams
                ORDER BY name
                LIMIT 15
                """
            )
            gn_rows = fetch_all(
                f"""
                SELECT DISTINCT TRIM(t.gym_name) AS gym_name
                FROM cheer_mvp_teams t
                INNER JOIN cheer_mvp_performances p
                  ON {_MVP_SCORED_PERF_ON_TEAM.strip()}
                WHERE t.gym_name IS NOT NULL AND LENGTH(TRIM(t.gym_name)) > 0
                ORDER BY gym_name
                LIMIT 400
                """
            )
            gym_names = [str(r["gym_name"]) for r in gn_rows if r.get("gym_name")]

            if gym_trim:
                meets = fetch_all(
                    f"""
                    SELECT DISTINCT m.meet_key, m.name, m.location, m.start_date, m.end_date,
                           m.starts_at, m.ends_at
                    FROM cheer_mvp_meets m
                    INNER JOIN cheer_mvp_performances p
                      ON {_MVP_SCORED_PERF_ON.strip()}
                    INNER JOIN cheer_mvp_teams t ON t.id = p.team_id
                    WHERE LOWER(TRIM(COALESCE(t.gym_name, ''))) = LOWER(TRIM(:gym))
                    ORDER BY m.start_date DESC NULLS LAST, m.name
                    LIMIT 120
                    """,
                    {"gym": gym_trim},
                )
            else:
                meets = fetch_all(
                    f"""
                    SELECT m.meet_key, m.name, m.location, m.start_date, m.end_date, m.starts_at, m.ends_at
                    FROM cheer_mvp_meets m
                    WHERE {_MVP_MEET_HAS_SCORES_SQL.strip()}
                    ORDER BY m.start_date DESC NULLS LAST, m.name
                    LIMIT 120
                    """
                )
        else:
            teams = fetch_all(
                """
                SELECT id, name, gym_name, level, division
                FROM cheer_mvp_teams
                WHERE
                  LOWER(name) LIKE :q
                  OR LOWER(COALESCE(gym_name, '')) LIKE :q
                  OR LOWER(COALESCE(division, '')) LIKE :q
                  OR LOWER(COALESCE(level, '')) LIKE :q
                ORDER BY name
                LIMIT 25
                """,
                {"q": needle},
            )
            if gym_trim:
                meets = fetch_all(
                    f"""
                    SELECT DISTINCT m.meet_key, m.name, m.location, m.start_date, m.end_date,
                           m.starts_at, m.ends_at
                    FROM cheer_mvp_meets m
                    INNER JOIN cheer_mvp_performances p
                      ON {_MVP_SCORED_PERF_ON.strip()}
                    INNER JOIN cheer_mvp_teams t ON t.id = p.team_id
                    WHERE LOWER(TRIM(COALESCE(t.gym_name, ''))) = LOWER(TRIM(:gym))
                      AND (
                        LOWER(m.name) LIKE :q
                        OR LOWER(m.meet_key) LIKE :q
                        OR LOWER(COALESCE(m.location, '')) LIKE :q
                      )
                    ORDER BY m.start_date DESC NULLS LAST, m.name
                    LIMIT 25
                    """,
                    {"q": needle, "gym": gym_trim},
                )
            else:
                meets = fetch_all(
                    f"""
                    SELECT m.meet_key, m.name, m.location, m.start_date, m.end_date, m.starts_at, m.ends_at
                    FROM cheer_mvp_meets m
                    WHERE
                      {_MVP_MEET_HAS_SCORES_SQL.strip()}
                      AND (
                        LOWER(m.name) LIKE :q
                        OR LOWER(m.meet_key) LIKE :q
                        OR LOWER(COALESCE(m.location, '')) LIKE :q
                      )
                    ORDER BY m.start_date DESC NULLS LAST, m.name
                    LIMIT 25
                    """,
                    {"q": needle},
                )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    out: dict[str, Any] = {
        "q": q.strip(),
        "teams": [_row(t) for t in teams],
        "meets": [_row(m) for m in meets],
    }
    if not q.strip():
        out["gym_names"] = gym_names
    return out


@router.get("/upcoming-meets")
def mvp_upcoming_meets(limit: int = Query(3, ge=1, le=25)):
    """
    Next competitions from ``cheer_mvp_meets`` that still look upcoming, excluding
    rebroadcasts (case-insensitive ``REBROADCAST`` in name). Uses DB rows filled by ingest
    (Varsity event-ticker + results index), not a live Varsity call from this service.
    """
    try:
        meets = fetch_all(
            """
            SELECT meet_key, name, location, start_date, end_date, starts_at, ends_at
            FROM cheer_mvp_meets
            WHERE
              LOWER(COALESCE(name, '')) NOT LIKE '%rebroadcast%'
              AND (ends_at IS NULL OR ends_at >= NOW())
              AND (
                (starts_at IS NOT NULL AND starts_at >= NOW())
                OR (
                  starts_at IS NULL
                  AND start_date IS NOT NULL
                  AND start_date >= CURRENT_DATE
                )
              )
            ORDER BY starts_at ASC NULLS LAST, start_date ASC NULLS LAST, name ASC
            LIMIT :lim
            """,
            {"lim": limit},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"limit": limit, "meets": [_row(m) for m in meets]}


@router.get("/meet/{meet_key}/timeline")
def mvp_meet_timeline(
    meet_key: str,
    session_id: Optional[int] = Query(None, description="Filter to one session; omit for all."),
):
    try:
        meet = fetch_one(
            """
            SELECT id, meet_key, name, location, start_date, end_date, source, starts_at, ends_at
            FROM cheer_mvp_meets
            WHERE meet_key = :meet_key
            """,
            {"meet_key": meet_key},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not meet:
        return JSONResponse({"error": "meet_not_found", "meet_key": meet_key}, status_code=404)

    mid = int(meet["id"])
    try:
        sessions = fetch_all(
            """
            SELECT id, name, display_order, start_time
            FROM cheer_mvp_sessions
            WHERE meet_id = :mid
            ORDER BY display_order, id
            """,
            {"mid": mid},
        )
        params: dict[str, Any] = {"mid": mid}
        session_filter = ""
        if session_id is not None:
            session_filter = "AND p.session_id = :sid"
            params["sid"] = session_id

        rows = fetch_all(
            f"""
            SELECT
              p.id AS performance_id,
              p.display_order,
              p.scheduled_time,
              p.actual_time,
              p.status,
              p.is_break,
              p.break_label,
              p.round,
              p.final_score,
              p.raw_score,
              p.performance_score,
              p.rank,
              p.deductions,
              p.team_id,
              t.name AS team_name,
              t.gym_name AS team_gym_name,
              t.level AS team_level,
              t.division AS team_division,
              s.id AS session_id,
              s.name AS session_name,
              s.display_order AS session_display_order
            FROM cheer_mvp_performances p
            LEFT JOIN cheer_mvp_teams t ON t.id = p.team_id
            JOIN cheer_mvp_sessions s ON s.id = p.session_id
            WHERE p.meet_id = :mid
            {session_filter}
            ORDER BY s.display_order, p.display_order, p.id
            """,
            params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "meet_key": meet_key,
        "meet": _row(dict(meet)),
        "sessions": [_row(s) for s in sessions],
        "items": [_row(r) for r in rows],
    }


@router.get("/meet/{meet_key}/results")
def mvp_meet_results(
    meet_key: str,
    session_id: Optional[int] = Query(None),
):
    try:
        meet = fetch_one(
            """
            SELECT id, meet_key, name, location, start_date, end_date, source, starts_at, ends_at
            FROM cheer_mvp_meets
            WHERE meet_key = :meet_key
            """,
            {"meet_key": meet_key},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not meet:
        return JSONResponse({"error": "meet_not_found", "meet_key": meet_key}, status_code=404)

    mid = int(meet["id"])
    params: dict[str, Any] = {"mid": mid}
    session_filter = ""
    if session_id is not None:
        session_filter = "AND p.session_id = :sid"
        params["sid"] = session_id

    try:
        rows = fetch_all(
            f"""
            SELECT
              p.rank,
              p.final_score,
              p.raw_score,
              p.performance_score,
              p.deductions,
              p.scheduled_time,
              p.actual_time,
              t.name AS team_name,
              t.gym_name AS team_gym_name,
              t.level AS team_level,
              t.division AS team_division,
              s.name AS session_name,
              p.session_id,
              p.round
            FROM cheer_mvp_performances p
            JOIN cheer_mvp_teams t ON t.id = p.team_id
            JOIN cheer_mvp_sessions s ON s.id = p.session_id
            WHERE p.meet_id = :mid
              AND p.is_break = false
              AND p.final_score IS NOT NULL
            {session_filter}
            ORDER BY
              p.rank NULLS LAST,
              p.final_score DESC,
              t.name
            """,
            params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "meet_key": meet_key,
        "meet": _row(dict(meet)),
        "session_id": session_id,
        "results": [_row(r) for r in rows],
    }
