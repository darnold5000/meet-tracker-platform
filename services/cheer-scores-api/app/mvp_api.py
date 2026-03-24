"""Cheer MVP JSON API: search, meet timeline, results."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from cheer_scores.db import fetch_all, fetch_one

router = APIRouter(prefix="/api/mvp", tags=["mvp"])


def _json_val(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_val(v) for k, v in r.items()}


@router.get("/search")
def mvp_search(q: str = Query("", min_length=0, max_length=200)):
    try:
        needle = f"%{q.strip().lower()}%"
        if not q.strip():
            teams = fetch_all(
                """
                SELECT id, name, gym_name, level, division
                FROM cheer_mvp_teams
                ORDER BY name
                LIMIT 15
                """
            )
            meets = fetch_all(
                """
                SELECT meet_key, name, location, start_date, end_date
                FROM cheer_mvp_meets
                ORDER BY start_date DESC NULLS LAST, name
                LIMIT 15
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
            meets = fetch_all(
                """
                SELECT meet_key, name, location, start_date, end_date
                FROM cheer_mvp_meets
                WHERE
                  LOWER(name) LIKE :q
                  OR LOWER(meet_key) LIKE :q
                  OR LOWER(COALESCE(location, '')) LIKE :q
                ORDER BY start_date DESC NULLS LAST, name
                LIMIT 25
                """,
                {"q": needle},
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "q": q.strip(),
        "teams": [_row(t) for t in teams],
        "meets": [_row(m) for m in meets],
    }


@router.get("/meet/{meet_key}/timeline")
def mvp_meet_timeline(
    meet_key: str,
    session_id: Optional[int] = Query(None, description="Filter to one session; omit for all."),
):
    try:
        meet = fetch_one(
            """
            SELECT id, meet_key, name, location, start_date, end_date, source
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
            SELECT id, meet_key, name, location, start_date, end_date, source
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
              p.deductions,
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
