"""
Varsity TV (FloSports) JSON + HTML helpers.

Uses public tv-admin and api.flosports.tv endpoints (no Playwright).
Schedule-style rows come from the event-ticker partial; concluded meets from
``/api/experiences/web/results`` (paginated). **Per-event results** (divisions,
scores) come from ``/event-hub/{event_id}/results`` (paginated ``table`` sections).
Rankings metadata from ``/api/experiences/web/rankings``; leaderboard tables are HTML fragments.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any, Dict, Iterator, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
DEFAULT_UA = os.getenv(
    "VARSITY_TV_USER_AGENT",
    "Mozilla/5.0 (compatible; MeetTracker/1.0; +https://github.com/meet-tracker)",
)

VARSITY_ADMIN_BASE = os.getenv(
    "VARSITY_TV_ADMIN_BASE", "https://tv-admin.varsity.com/api/experiences/web"
).rstrip("/")
VARSITY_SITE_ID = os.getenv("VARSITY_TV_SITE_ID", "20")
VARSITY_API_VERSION = os.getenv("VARSITY_TV_API_VERSION", "1.33.2")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA, "Accept": "application/json"})
    return s


def fetch_json(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """GET ``path`` relative to VARSITY_ADMIN_BASE (path must start with ``/``)."""
    url = f"{VARSITY_ADMIN_BASE}{path}"
    params = dict(params or {})
    params.setdefault("site_id", VARSITY_SITE_ID)
    params.setdefault("version", VARSITY_API_VERSION)
    r = _session().get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _walk(obj: Any, visit) -> None:
    if isinstance(obj, dict):
        visit(obj)
        for v in obj.values():
            _walk(v, visit)
    elif isinstance(obj, list):
        for x in obj:
            _walk(x, visit)


def iter_nodes_of_type(root: Any, node_type: str) -> Iterator[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    def visit(d: Dict[str, Any]) -> None:
        if d.get("type") == node_type:
            found.append(d)

    _walk(root, visit)
    yield from found


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    s = value.replace("+0000", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        logger.debug("Could not parse datetime %r", value)
        return None


def normalize_event_card(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a ``card:event`` from schedule or results listings."""
    if card.get("type") != "card:event":
        return None
    action = card.get("action") or {}
    analytics = action.get("analytics") or {}
    event_id = analytics.get("nodeId") or analytics.get("entityId")
    if event_id is None:
        return None
    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        return None

    cta2 = card.get("cta2") or {}
    results_path = None
    if (cta2.get("title") or "").strip().lower() == "results":
        results_path = cta2.get("url")

    lp = card.get("label1Parts") or {}
    start_dt = _parse_iso_datetime(lp.get("startDateTime"))
    end_dt = _parse_iso_datetime(lp.get("endDateTime"))

    return {
        "source": "varsity_tv",
        "event_id": eid,
        "title": (card.get("title") or "").strip() or None,
        "subtitle": (card.get("subtitle1") or "").strip() or None,
        "status": lp.get("status"),
        "start_at": start_dt,
        "end_at": end_dt,
        "tv_path": action.get("url"),
        "slug_uri": analytics.get("slugUri"),
        "results_path": results_path,
    }


def fetch_schedule_events() -> List[Dict[str, Any]]:
    """Upcoming / featured events from the home-page ticker (Schedule hub)."""
    data = fetch_json(
        "/partials/event-ticker",
        params={
            "limit": 50,
            "isNextGenEventHub": "false",
        },
    )
    body = data.get("data") or data.get("body") or {}
    out: List[Dict[str, Any]] = []
    for card in iter_nodes_of_type(body, "card:event"):
        row = normalize_event_card(card)
        if row:
            out.append(row)
    logger.info("Varsity schedule (event-ticker): %d events", len(out))
    return out


def iter_results_events(
    page_size: int = 20, max_events: Optional[int] = None
) -> Iterator[Dict[str, Any]]:
    """Paginated concluded / results listing (``card:event``)."""
    offset = 0
    yielded = 0
    while True:
        payload = fetch_json(
            "/results",
            params={"limit": page_size, "offset": offset},
        )
        batch: List[Dict[str, Any]] = []
        for card in iter_nodes_of_type(payload, "card:event"):
            row = normalize_event_card(card)
            if row:
                batch.append(row)
        if not batch:
            break
        for row in batch:
            yield row
            yielded += 1
            if max_events is not None and yielded >= max_events:
                return
        if len(batch) < page_size:
            break
        offset += page_size


def fetch_varsity_listing_row_for_event(
    event_id: int, *, max_results_scan: int = 400
) -> Optional[Dict[str, Any]]:
    """
    Find one normalized ``card:event`` row for ``event_id`` from the schedule ticker
    and paginated results index (location/subtitle + dates + title).
    """
    for row in fetch_schedule_events():
        if row.get("event_id") == event_id:
            return row
    for row in iter_results_events(max_events=max_results_scan):
        if row.get("event_id") == event_id:
            return row
    return None


def infer_team_level_from_division_label(label: str) -> Optional[str]:
    """
    Best-effort level string from a results table division label
    (e.g. ``L1 Tiny - Novice - Restrictions Finals`` -> ``L1 Tiny - Novice``).
    """
    if not label or not isinstance(label, str):
        return None
    base = label.strip()
    base = re.sub(r"\s+(prelims?|semi-?finals?|finals?)\s*$", "", base, flags=re.I).strip()
    parts = [p.strip() for p in base.split(" - ") if p.strip()]
    if not parts:
        return None
    if re.match(r"^L[\d.]+", parts[0], re.I):
        if len(parts) >= 2 and not re.match(r"^L[\d.]+", parts[1], re.I):
            return f"{parts[0]} - {parts[1]}"[:64]
        return parts[0][:64]
    if len(parts) >= 2:
        return f"{parts[0]} - {parts[1]}"[:64]
    return parts[0][:64]


def fetch_ranking_hub_cards() -> List[Dict[str, Any]]:
    """Top-level ranking / standings entry cards (title, link, node id when present)."""
    payload = fetch_json("/rankings", params={})
    cards: List[Dict[str, Any]] = []
    for item in iter_nodes_of_type(payload, "card"):
        action = item.get("action") or {}
        analytics = action.get("analytics") or {}
        node_id = analytics.get("nodeId") or analytics.get("entityId")
        cards.append(
            {
                "card_id": item.get("id"),
                "title": item.get("title"),
                "subtitle": item.get("subtitle1"),
                "url": action.get("url"),
                "share_url": action.get("shareUrl"),
                "ranking_node_id": int(node_id) if node_id is not None else None,
                "node_type": analytics.get("nodeType"),
            }
        )
    logger.info("Varsity rankings hub: %d cards", len(cards))
    return cards


def fetch_ranking_layout(ranking_id: int) -> Dict[str, Any]:
    """``layout:ranking`` payload including ``sets[].rankings[].tableHtmlUrl``."""
    return fetch_json(f"/rankings/{int(ranking_id)}", params={})


def iter_ranking_table_urls(
    ranking_document_id: int, layout: Dict[str, Any]
) -> Iterator[Dict[str, Any]]:
    if (layout.get("type") or "") != "layout:ranking":
        return
    for day in layout.get("sets") or []:
        for rk in day.get("rankings") or []:
            url = rk.get("tableHtmlUrl")
            if not url:
                continue
            yield {
                "ranking_document_id": ranking_document_id,
                "layout_title": layout.get("title"),
                "publish_set_id": day.get("id"),
                "publish_set_name": day.get("name"),
                "section_id": rk.get("id"),
                "section_name": rk.get("name"),
                "headline": rk.get("headline"),
                "table_html_url": url,
                "share_url": rk.get("shareUrl"),
            }


def fetch_ranking_table_rows(table_html_url: str) -> List[List[str]]:
    """Download embedded ranking HTML and return table rows as lists of cell text."""
    r = _session().get(table_html_url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    table = soup.find("table")
    if not table:
        return []
    rows: List[List[str]] = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def merge_events_by_id(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Later groups override earlier rows with the same ``event_id``."""
    by_id: Dict[int, Dict[str, Any]] = {}
    for group in groups:
        for row in group:
            eid = row.get("event_id")
            if isinstance(eid, int):
                by_id[eid] = row
    return list(by_id.values())


def varsity_event_to_cheer_mvp_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map normalized event row to CheerMvpMeet constructor kwargs (subset)."""
    start = row.get("start_at")
    end = row.get("end_at")
    return {
        "meet_key": f"VARSITY-{row['event_id']}",
        "name": row.get("title") or generic_varsity_event_label(int(row["event_id"])),
        "location": row.get("subtitle"),
        "start_date": start.date() if isinstance(start, datetime) else None,
        "end_date": end.date() if isinstance(end, datetime) else None,
        "source": "varsity_tv",
    }


def sync_cheer_mvp_meets_from_varsity(
    db: Session, results_max_items: Optional[int] = None
) -> Dict[str, int]:
    """
    Upsert CheerMvpMeet rows from Varsity schedule + results listing.

    ``db`` is a SQLAlchemy Session. Commits once on success.
    Returns counts: inserted, updated, total_merged.
    """
    from db.mvp_models import CheerMvpMeet

    schedule = fetch_schedule_events()
    results: List[Dict[str, Any]] = []
    for row in iter_results_events():
        results.append(row)
        if results_max_items is not None and len(results) >= results_max_items:
            break
    merged = merge_events_by_id(schedule, results)

    inserted = updated = 0
    for fields in merged:
        kwargs = varsity_event_to_cheer_mvp_fields(fields)
        existing = (
            db.query(CheerMvpMeet)
            .filter(CheerMvpMeet.meet_key == kwargs["meet_key"])
            .first()
        )
        if existing:
            changed = False
            for k in ("name", "location", "start_date", "end_date", "source"):
                nv = kwargs.get(k)
                if nv is not None and getattr(existing, k) != nv:
                    setattr(existing, k, nv)
                    changed = True
            if changed:
                updated += 1
        else:
            db.add(CheerMvpMeet(**kwargs))
            inserted += 1
    db.commit()
    return {"inserted": inserted, "updated": updated, "total_merged": len(merged)}


def parse_varsity_event_id_from_meet_key(meet_key: str) -> Optional[int]:
    """Return Varsity numeric event id if ``meet_key`` is ``VARSITY-<digits>``."""
    prefix = "VARSITY-"
    if not meet_key or not str(meet_key).startswith(prefix):
        return None
    rest = str(meet_key)[len(prefix) :].strip()
    if not rest.isdigit():
        return None
    return int(rest)


def cheer_mvp_meet_covers_calendar_day(
    start_date: Optional[date],
    end_date: Optional[date],
    on_day: date,
    *,
    include_undated: bool = False,
) -> bool:
    """
    True if ``on_day`` is on or between the meet's ``start_date`` and ``end_date``
    (inclusive). If only ``start_date`` is set, treats the meet as a single day.
    If both dates are missing, returns ``include_undated``.
    """
    if start_date is None and end_date is None:
        return include_undated
    start = start_date or on_day
    end = end_date or start_date or on_day
    return start <= on_day <= end


# ── Single-event results (event hub) ─────────────────────────────────────────


def _unwrap_event_hub_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("type") == "partial:list" and isinstance(payload.get("data"), dict):
        return payload["data"]
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else payload


def generic_varsity_event_label(event_id: int) -> str:
    """Fallback label when no real event title is known."""
    return f"Varsity event {int(event_id)}"


def _is_plausible_event_title(name: str) -> bool:
    """Heuristic: full event names from analytics (not division filters, replay links, etc.)."""
    s = name.strip()
    if len(s) < 18:
        return False
    low = s.lower()
    if low in ("replay link",):
        return False
    # Division / filter lines from the same payload shapes
    if re.match(r"^l\d", low) and " - " in s:
        return False
    if re.match(r"^\d{4}\s+", s):
        return True
    if any(x in low for x in ("championship", "nationals", "classic", "showcase", "challenge cup")):
        return True
    if len(s) >= 42:
        return True
    return False


def _title_from_events_slug_uri(uri: str, event_id: int) -> Optional[str]:
    m = re.search(rf"/events/{int(event_id)}-([a-z0-9-]+)/?(?:\?|$)", uri, re.I)
    if not m:
        return None
    slug = m.group(1)
    if not slug or slug.isdigit():
        return None
    return " ".join(p.capitalize() for p in slug.split("-"))


def extract_event_display_title_from_hub_payload(
    payload: Dict[str, Any], event_id: int
) -> Optional[str]:
    """
    Varsity event-hub /results JSON embeds the real event name in ``analytics.name`` on
    section actions (e.g. \"2026 CHEERSPORT …\") and in ``slugUri`` paths.
    """
    inner = _unwrap_event_hub_payload(payload)
    candidates: List[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            an = o.get("analytics")
            if isinstance(an, dict):
                nm = an.get("name")
                if isinstance(nm, str) and _is_plausible_event_title(nm):
                    candidates.append(nm.strip())
            su = o.get("slugUri")
            if isinstance(su, str):
                t = _title_from_events_slug_uri(su, event_id)
                if t and _is_plausible_event_title(t):
                    candidates.append(t)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(inner)
    if not candidates:
        return None
    # Prefer the longest analytics-style title (usually the full championship name)
    candidates.sort(key=len, reverse=True)
    return candidates[0][:255]


def fetch_event_hub_display_title(event_id: int) -> Optional[str]:
    """GET first page of event-hub results and parse display title (one HTTP round-trip)."""
    try:
        payload = fetch_event_hub_results_page(event_id, limit=5, offset=0)
    except requests.RequestException as exc:
        logger.warning("Could not fetch event hub for title (event %s): %s", event_id, exc)
        return None
    return extract_event_display_title_from_hub_payload(payload, event_id)


def fetch_event_hub_results_page(
    event_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
    facets: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One page of structured results tables for a Varsity event.

    ``facets`` is the raw JSON string used by the site (e.g.
    ``{"class":"Cheer","category":"Level 1"}``) when narrowing filters.
    """
    params: Dict[str, Any] = {
        "site_id": VARSITY_SITE_ID,
        "version": VARSITY_API_VERSION,
        "limit": limit,
        "offset": offset,
    }
    if facets:
        params["facets"] = facets
    url = f"{VARSITY_ADMIN_BASE}/event-hub/{int(event_id)}/results"
    r = _session().get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def iter_event_hub_result_table_sections(
    event_id: int,
    *,
    page_size: int = 100,
    facets: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield each ``collection`` section that contains a ``table`` (division/round block)."""
    offset = 0
    while True:
        payload = fetch_event_hub_results_page(
            event_id, limit=page_size, offset=offset, facets=facets
        )
        inner = _unwrap_event_hub_payload(payload)
        sections = inner.get("sections") or []
        tables = [s for s in sections if (s.get("id") or "").startswith("id-table")]
        if not tables:
            break
        yield from tables
        if len(tables) < page_size:
            break
        offset += page_size


def _plain_text_from_data_blob(data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return ""
    t = data.get("type")
    if t == "text":
        base = (data.get("text") or "").strip()
        sub = (data.get("subText") or "").strip()
        if sub:
            return f"{base} / {sub}".strip()
        return base
    if t == "link":
        return (data.get("title") or data.get("url") or "").strip()
    return ""


def _program_team_names(cell: Optional[Dict[str, Any]]) -> tuple[str, str]:
    """Return (program_or_gym, team_name) from program/team column."""
    if not cell:
        return "", ""
    data = cell.get("data") or {}
    if data.get("type") == "text":
        program = (data.get("text") or "").strip()
        team = (data.get("subText") or "").strip()
        return program, team
    return _plain_text_from_data_blob(data), ""


def _cell_by_key(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for c in row.get("cells") or []:
        k = c.get("key")
        if k:
            out[k] = c
    return out


def _parse_score_float(value: str) -> Optional[float]:
    if not value or value in ("---", "–", "-"):
        return None
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return None


def _parse_rank_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    for prefix in ("t-", "T-"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_event_hub_table_section(event_id: int, section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse one results ``collection`` (one division/round) into flat score rows."""
    title = (section.get("title") or "").strip()
    rows_out: List[Dict[str, Any]] = []
    for item in section.get("items") or []:
        if item.get("type") != "table":
            continue
        for row in item.get("rows") or []:
            if row.get("type") != "table:row":
                continue
            by_k = _cell_by_key(row)
            program, team = _program_team_names(by_k.get("program-team"))
            rank_txt = _plain_text_from_data_blob((by_k.get("rank") or {}).get("data"))
            action = row.get("action") or {}
            mp = action.get("mergeParams") or {}
            rows_out.append(
                {
                    "event_id": event_id,
                    "division_round": title,
                    "rank_label": rank_txt,
                    "rank": _parse_rank_int(rank_txt),
                    "program": program,
                    "team": team,
                    "raw_score": _parse_score_float(
                        _plain_text_from_data_blob(
                            (by_k.get("raw-score") or {}).get("data")
                        )
                    ),
                    "deductions": _parse_score_float(
                        _plain_text_from_data_blob(
                            (by_k.get("deductions") or {}).get("data")
                        )
                    ),
                    "performance_score": _parse_score_float(
                        _plain_text_from_data_blob(
                            (by_k.get("performance-score") or {}).get("data")
                        )
                    ),
                    "event_score": _parse_score_float(
                        _plain_text_from_data_blob(
                            (by_k.get("event-score") or {}).get("data")
                        )
                    ),
                    "video_playing_id": mp.get("playing"),
                    "replay_path": action.get("url"),
                }
            )
    return rows_out


def iter_event_hub_result_rows(
    event_id: int,
    *,
    page_size: int = 100,
    facets: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """All score rows for an event (all pages, all division tables)."""
    for sec in iter_event_hub_result_table_sections(
        event_id, page_size=page_size, facets=facets
    ):
        yield from parse_event_hub_table_section(event_id, sec)


def sync_event_results_to_cheer_mvp(
    db: Session,
    event_id: int,
    *,
    meet_name: Optional[str] = None,
    page_size: int = 100,
    facets: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Replace Cheer MVP sessions/performances for ``VARSITY-{event_id}`` with
    rows from the event-hub results API. Teams are reused by (gym_name, name).

    Commits once. Returns counts and optional error.
    """
    from db.mvp_models import (
        CheerMvpMeet,
        CheerMvpPerformance,
        CheerMvpSession,
        CheerMvpTeam,
    )

    rows = list(
        iter_event_hub_result_rows(event_id, page_size=page_size, facets=facets)
    )
    if not rows:
        return {"error": "no_result_rows", "event_id": event_id, "performances": 0}

    meet_key = f"VARSITY-{event_id}"
    generic = generic_varsity_event_label(event_id)

    listing: Optional[Dict[str, Any]] = None
    try:
        listing = fetch_varsity_listing_row_for_event(event_id)
    except requests.RequestException as exc:
        logger.warning("Varsity listing lookup failed for event %s: %s", event_id, exc)

    cleaned = meet_name.strip() if meet_name and str(meet_name).strip() else ""
    if cleaned == generic:
        cleaned = ""
    display_name = cleaned if cleaned else None
    if not display_name:
        display_name = fetch_event_hub_display_title(event_id)
    if not display_name or display_name == generic:
        if listing:
            lt = (listing.get("title") or "").strip()
            if lt:
                display_name = lt[:255]
    if not display_name:
        display_name = generic
    display_name = display_name[:255]

    meet = db.query(CheerMvpMeet).filter(CheerMvpMeet.meet_key == meet_key).first()
    if meet:
        meet.name = display_name
        meet.source = "varsity_tv_results"
    else:
        meet = CheerMvpMeet(
            meet_key=meet_key, name=display_name, source="varsity_tv_results"
        )
        db.add(meet)
    db.flush()

    if listing:
        sub = (listing.get("subtitle") or "").strip()
        if sub:
            meet.location = sub[:255]
        st_at = listing.get("start_at")
        en_at = listing.get("end_at")
        if isinstance(st_at, datetime):
            meet.start_date = st_at.date()
        if isinstance(en_at, datetime):
            meet.end_date = en_at.date()
        elif isinstance(st_at, datetime) and meet.end_date is None:
            meet.end_date = st_at.date()

    db.query(CheerMvpPerformance).filter(CheerMvpPerformance.meet_id == meet.id).delete()
    db.query(CheerMvpSession).filter(CheerMvpSession.meet_id == meet.id).delete()
    db.flush()

    session_by_label: Dict[str, CheerMvpSession] = {}
    perf_counters: Dict[int, int] = {}

    def session_for(label: str) -> CheerMvpSession:
        if label not in session_by_label:
            s = CheerMvpSession(
                meet_id=meet.id,
                name=label[:255],
                display_order=len(session_by_label),
            )
            db.add(s)
            session_by_label[label] = s
            db.flush()
        return session_by_label[label]

    perf_n = 0
    for r in rows:
        label = (r.get("division_round") or "Results")[:255]
        sess = session_for(label)
        program = (r.get("program") or "").strip() or "Unknown program"
        team_nm = (r.get("team") or "").strip() or program
        level_guess = infer_team_level_from_division_label(label)

        team = (
            db.query(CheerMvpTeam)
            .filter(
                CheerMvpTeam.gym_name == program[:255],
                CheerMvpTeam.name == team_nm[:255],
            )
            .first()
        )
        if not team:
            team = CheerMvpTeam(
                name=team_nm[:255],
                gym_name=program[:255],
                level=level_guess,
                division=label[:255] if label else None,
                normalized_division=label[:255] if label else None,
            )
            db.add(team)
            db.flush()
        elif team.level is None and level_guess:
            team.level = level_guess

        sid = sess.id
        perf_counters[sid] = perf_counters.get(sid, 0) + 1
        es = r.get("event_score")
        rs = r.get("raw_score")
        ps = r.get("performance_score")
        perf = CheerMvpPerformance(
            meet_id=meet.id,
            session_id=sess.id,
            team_id=team.id,
            is_break=False,
            scheduled_time=None,
            status="final",
            display_order=perf_counters[sid] - 1,
            round=(r.get("division_round") or "")[:64] or None,
            final_score=float(es) if es is not None else None,
            raw_score=float(rs) if rs is not None else None,
            performance_score=float(ps) if ps is not None else None,
            rank=r.get("rank"),
            deductions=r.get("deductions"),
        )
        db.add(perf)
        perf_n += 1

    db.commit()
    return {
        "event_id": event_id,
        "meet_key": meet_key,
        "sessions": len(session_by_label),
        "performances": perf_n,
        "teams_touched": perf_n,
    }
