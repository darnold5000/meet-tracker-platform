from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env from this project, then from 06_usag_meet_tracker (shared DB)
PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR.parent / "06_usag_meet_tracker" / ".env")

from fastapi import FastAPI, Query, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Ensure `gym_scores/` is importable in environments that don't add the repo root
# to PYTHONPATH (e.g. Streamlit Community Cloud running this as an ASGI app).
sys.path.insert(0, str(PROJECT_DIR))

from gym_scores.db import fetch_all, fetch_one  # noqa: E402
# One-meet MVP (easy to extend later). This is the `meets.meet_id` value in the `06` DB.
DEFAULT_MEET_KEY = os.getenv("GYM_SCORES_MEET_KEY", "MSO-36478")
ALLOWED_MEET_IDS = [
    m.strip()
    for m in os.getenv(
        "GYM_SCORES_ALLOWED_MEET_IDS",
        "",
    ).split(",")
    if m.strip()
]


app = FastAPI(title="Gym Scores")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://gym-scores-web-617613197143.us-central1.run.app",
        "https://meetscores.app",
        "https://www.meetscores.app",
        "https://meetscores.live",
        "https://www.meetscores.live",
    ],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

static_dir = PROJECT_DIR / "app" / "static"
templates = Jinja2Templates(directory=str(PROJECT_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    try:
        meet = _get_meet(DEFAULT_MEET_KEY)
    except RuntimeError as exc:
        return HTMLResponse(f"Database not configured: {exc}", status_code=503)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "meet_key": DEFAULT_MEET_KEY,
            "latest": None,
            "meet": meet,
        },
    )


@app.get("/meet/{meet_key}", response_class=HTMLResponse)
def meet_view(
    request: Request,
    meet_key: str,
    level: str = Query("All"),
    division: str = Query("All"),
    q: str = Query(""),
):
    try:
        meet = _get_meet(meet_key)
    except RuntimeError as exc:
        return HTMLResponse(f"Database not configured: {exc}", status_code=503)
    if not meet:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "meet_key": meet_key, "latest": None, "meet": None},
            status_code=404,
        )

    levels = ["All"] + _list_distinct(meet_id=int(meet["id"]), column="level")
    divisions = ["All"] + _list_distinct(meet_id=int(meet["id"]), column="division")

    data = _load_meet_rows(meet_id=int(meet["id"]), level=level, division=division, q=q, gym="", limit=800)
    return templates.TemplateResponse(
        "meet.html",
        {
            "request": request,
            "meet_key": meet_key,
            "levels": levels,
            "divisions": divisions,
            "sessions": ["All"],  # sessions aren't persisted in `scores` yet
            "selected": {"session": "All", "level": level, "division": division, "q": q},
            "initial_data": data,
        },
    )


@app.get("/api/meet/{meet_key}/scores", response_class=JSONResponse)
def api_scores(
    meet_key: str,
    level: str = Query("All"),
    division: str = Query("All"),
    q: str = Query(""),
    gym: str = Query(""),
    athlete: str = Query("All"),
    session: str = Query("All"),
    limit: int = Query(500, ge=1, le=2000),
):
    try:
        meet = _get_meet(meet_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Database not configured: {exc}") from exc
    if not meet:
        return JSONResponse({"error": "meet_not_found", "meet_key": meet_key}, status_code=404)
    rows = _load_meet_rows(
        meet_id=int(meet["id"]),
        level=level,
        division=division,
        q=q,
        gym=gym,
        athlete=athlete,
        session=session,
        limit=limit,
    )
    return {
        "meet_key": meet_key,
        "meet": {
            "name": meet.get("name"),
            "location": meet.get("location"),
            "facility": meet.get("facility"),
            "host_gym": meet.get("host_gym"),
            "state": meet.get("state"),
            "start_date": meet.get("start_date"),
            "end_date": meet.get("end_date"),
        },
        "latest": None,
        "count": len(rows),
        "rows": rows,
    }


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {
            "name": "Gym Scores",
            "short_name": "GymScores",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f1d3a",
            "theme_color": "#0f1d3a",
            "icons": [
                {"src": "/static/icons/icon.svg", "sizes": "any", "type": "image/svg+xml"},
            ],
        }
    )


@app.get("/sw.js")
def service_worker():
    # served from root for PWA scope
    sw_path = static_dir / "sw.js"
    return HTMLResponse(sw_path.read_text(encoding="utf-8"), media_type="application/javascript")


@app.get("/api/meets", response_class=JSONResponse)
def api_meets():
    if not ALLOWED_MEET_IDS:
        return {"meets": []}
    try:
        meets = _list_allowed_meets(ALLOWED_MEET_IDS)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Database not configured: {exc}") from exc
    return {"meets": meets}


@app.get("/api/meet/{meet_key}/sessions", response_class=JSONResponse)
def api_meet_sessions(meet_key: str):
    try:
        meet = _get_meet(meet_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Database not configured: {exc}") from exc
    if not meet:
        return JSONResponse({"error": "meet_not_found", "meet_key": meet_key}, status_code=404)

    def format_session(row: dict[str, Any]) -> str:
        session_number = row.get("session_number")
        start_time = row.get("start_time")

        parts: list[str] = []
        if session_number is not None:
            parts.append(f"Session {session_number}")
        if start_time is not None:
            try:
                day = start_time.day  # works for datetime/date
                mon = start_time.strftime("%b")
                parts.append(f"{mon} {day}")
            except Exception:
                pass
        if not parts:
            sid = row.get("session_id")
            return f"Session {sid}" if sid is not None else "Session"
        return " · ".join(parts)

    rows = fetch_all(
        """
        SELECT DISTINCT
          sess.id AS session_id,
          sess.session_number AS session_number,
          sess.start_time AS start_time
        FROM sessions sess
        JOIN scores s ON s.session_id = sess.id
        WHERE sess.meet_id = :meet_db_id
        ORDER BY sess.start_time DESC NULLS LAST, sess.session_number, sess.id
        """,
        {"meet_db_id": int(meet["id"])},
    )

    return {
        "meet_key": meet_key,
        "sessions": [{"session_id": str(r["session_id"]), "label": format_session(r)} for r in rows],
    }


@app.get("/api/meet/{meet_key}/athletes", response_class=JSONResponse)
def api_meet_athletes(
    meet_key: str,
    level: str = Query("All"),
    division: str = Query("All"),
    gym: str = Query(""),
    session: str = Query("All"),
):
    try:
        meet = _get_meet(meet_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Database not configured: {exc}") from exc
    if not meet:
        return JSONResponse({"error": "meet_not_found", "meet_key": meet_key}, status_code=404)

    where: list[str] = ["s.meet_id = :meet_id", "s.event IN ('AA','VT','UB','BB','FX')"]
    params: dict[str, Any] = {"meet_id": int(meet["id"])}

    if level and level != "All":
        where.append("s.level = :level")
        params["level"] = level
    if division and division != "All":
        where.append("s.division = :division")
        params["division"] = division
    if gym and gym.strip():
        where.append("LOWER(g.canonical_name) = :gym")
        params["gym"] = gym.strip().lower()
    if session and session != "All":
        try:
            params["session_id"] = int(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="session must be a session_id") from exc
        where.append("s.session_id = :session_id")

    where.append("a.canonical_name IS NOT NULL")
    where.append("TRIM(a.canonical_name) != ''")

    rows = fetch_all(
        f"""
        SELECT DISTINCT a.canonical_name AS athlete
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        WHERE {' AND '.join(where)}
        ORDER BY athlete
        """,
        params,
    )
    athletes = [str(r["athlete"]) for r in rows if r.get("athlete")]
    return {"meet_key": meet_key, "athletes": athletes}


def _get_meet(meet_key: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, meet_id, name, location, facility, host_gym, state, start_date, end_date, mso_url
        FROM meets
        WHERE meet_id = :meet_id
        """,
        {"meet_id": meet_key},
    )


def _list_allowed_meets(meet_ids: list[str]) -> list[dict]:
    if not meet_ids:
        return []
    params = {f"m{i}": mid for i, mid in enumerate(meet_ids)}
    placeholders = ", ".join(f":m{i}" for i in range(len(meet_ids)))
    return fetch_all(
        f"""
        SELECT DISTINCT
          m.meet_id,
          m.name,
          m.location,
          m.facility,
          m.host_gym,
          m.state,
          m.start_date,
          m.end_date
        FROM meets m
        JOIN scores s ON s.meet_id = m.id
        WHERE m.meet_id IN ({placeholders})
        ORDER BY m.start_date DESC NULLS LAST, m.name
        """,
        params,
    )


def _list_distinct(meet_id: int, column: str) -> list[str]:
    if column not in {"level", "division"}:
        raise ValueError("unsupported column")
    rows = fetch_all(
        f"""
        SELECT DISTINCT {column} AS v
        FROM scores
        WHERE meet_id = :meet_id AND {column} IS NOT NULL AND TRIM({column}) != ''
        ORDER BY v
        """,
        {"meet_id": meet_id},
    )
    return [str(r["v"]) for r in rows if r.get("v")]


def _load_meet_rows(
    meet_id: int,
    *,
    level: str,
    division: str,
    q: str,
    gym: str = "",
    athlete: str = "All",
    session: str = "All",
    limit: int,
) -> list[dict[str, Any]]:
    where = ["s.meet_id = :meet_id", "s.event IN ('AA','VT','UB','BB','FX')"]
    # `limit` is the number of athlete cards. Fetch more underlying score rows so we
    # can assemble complete VT/UB/BB/FX cards even when limit is small.
    raw_limit = max(int(limit) * 8, 5000)
    params: dict[str, Any] = {"meet_id": meet_id, "limit": raw_limit}
    if level and level != "All":
        where.append("s.level = :level")
        params["level"] = level
    if division and division != "All":
        where.append("s.division = :division")
        params["division"] = division
    if q and q.strip():
        where.append("(LOWER(a.canonical_name) LIKE :q OR LOWER(g.canonical_name) LIKE :q)")
        params["q"] = f"%{q.strip().lower()}%"
    if gym and gym.strip():
        where.append("LOWER(g.canonical_name) = :gym")
        params["gym"] = gym.strip().lower()
    if athlete and athlete != "All" and athlete.strip():
        where.append("LOWER(a.canonical_name) = :athlete")
        params["athlete"] = athlete.strip().lower()
    if session and session != "All":
        try:
            params["session_id"] = int(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="session must be a session_id") from exc
        where.append("s.session_id = :session_id")

    def format_session(row: dict[str, Any]) -> str:
        session_number = row.get("session_number")
        start_time = row.get("session_start_time")

        parts: list[str] = []
        if session_number is not None:
            parts.append(f"Session {session_number}")
        if start_time is not None:
            try:
                day = start_time.day  # works for datetime/date
                mon = start_time.strftime("%b")
                parts.append(f"{mon} {day}")
            except Exception:
                pass
        if not parts:
            sid = row.get("session_id")
            return f"Session {sid}" if sid is not None else ""
        return " · ".join(parts)

    rows = fetch_all(
        f"""
        SELECT
          a.id AS athlete_id,
          a.canonical_name AS athlete,
          COALESCE(g.canonical_name, '') AS gym,
          s.level AS level,
          s.division AS division,
          s.event AS event,
          s.score AS score,
          s.place AS place
          , s.session_id AS session_id
          , sess.session_number AS session_number
          , sess.start_time AS session_start_time
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        LEFT JOIN sessions sess ON sess.id = s.session_id
        WHERE {' AND '.join(where)}
        ORDER BY s.score DESC
        LIMIT :limit
        """,
        params,
    )

    # Pivot into the mobile card shape (one row per athlete+level+division)
    by_key: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (r["athlete_id"], r.get("session_id"), r.get("level") or "", r.get("division") or "")
        if key not in by_key:
            by_key[key] = {
                "athlete": r["athlete"],
                "gym": r["gym"],
                "session": format_session(r),
                "level": r.get("level") or "",
                "division": r.get("division") or "",
                "aa": {"score": None, "place": None},
                "vt": {"score": None, "place": None},
                "ub": {"score": None, "place": None},
                "bb": {"score": None, "place": None},
                "fx": {"score": None, "place": None},
            }

        ev = str(r["event"] or "").upper()
        target = None
        if ev == "AA":
            target = "aa"
        elif ev == "VT":
            target = "vt"
        elif ev == "UB":
            target = "ub"
        elif ev == "BB":
            target = "bb"
        elif ev == "FX":
            target = "fx"
        if not target:
            continue

        cur = by_key[key][target]
        score = float(r["score"]) if r["score"] is not None else None
        place = int(r["place"]) if r.get("place") is not None else None

        # Keep best score per event (and its place)
        if cur["score"] is None or (score is not None and score > cur["score"]):
            cur["score"] = score
            cur["place"] = place

    out = list(by_key.values())
    out.sort(key=lambda x: (x["aa"]["score"] is None, -(x["aa"]["score"] or 0.0), x["athlete"]))
    return out[: int(limit)]

