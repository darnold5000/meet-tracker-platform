"""
Varsity TV (FloSports) JSON + HTML helpers.

Uses public tv-admin and api.flosports.tv endpoints (no Playwright).
Schedule-style rows come from the JSON ``/partials/event-ticker`` endpoint (the same feed as the
site’s schedule hub), not from scraping an HTML schedule URL. Concluded meets from
``/api/experiences/web/results`` (paginated). **Per-event results** (divisions,
scores) come from ``/event-hub/{event_id}/results`` (paginated ``table`` sections).
Those JSON tables are often **truncated** (preview); full standings match
``tv.varsity.com/events/<id-or-slug>/results/view-all?facets=…`` HTML, which we merge when
``CHEER_HUB_VIEW_ALL_HTML`` is enabled (default). Path segment prefers hub ``slugUri``
(e.g. ``14478900-2026-one-up-grand-nationals``). **Flo may respond HTTP 406** to HTML
from some datacenter IPs; set ``CHEER_HUB_VIEW_ALL_HTTPS_PROXY`` (or run ingest where
HTML is allowed) to unblock.

Rankings metadata from ``/api/experiences/web/rankings``; leaderboard tables are HTML fragments.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

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
VARSITY_TV_PUBLIC_ORIGIN = os.getenv(
    "VARSITY_TV_PUBLIC_ORIGIN", "https://tv.varsity.com"
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


def varsity_display_name_has_rebroadcast(name: Optional[str]) -> bool:
    """True if a meet / event title is a Varsity TV rebroadcast (case-insensitive)."""
    return "REBROADCAST" in (name or "").upper()


def varsity_event_title_has_rebroadcast(row: Dict[str, Any]) -> bool:
    """True if the normalized card's title looks like a rebroadcast."""
    return varsity_display_name_has_rebroadcast((row.get("title") or "").strip() or None)


def top_upcoming_schedule_events_from_ticker(
    *, limit: int = 3, exclude_rebroadcast: bool = True
) -> List[Dict[str, Any]]:
    """
    Next ``limit`` events from the event-ticker partial, ordered by ``start_at``.

    This is the same JSON feed the Varsity site uses for the schedule hub strip — not an
    HTML scrape of a schedule URL. Rows without ``start_at`` are appended after all
    future-dated rows, preserving ticker order.
    """
    if limit < 1:
        return []
    raw = fetch_schedule_events()
    if exclude_rebroadcast:
        raw = [r for r in raw if not varsity_event_title_has_rebroadcast(r)]
    now = datetime.now(timezone.utc)
    dated_future: List[tuple[datetime, Dict[str, Any]]] = []
    undated: List[Dict[str, Any]] = []
    for r in raw:
        sa = r.get("start_at")
        if isinstance(sa, datetime):
            aware = sa if sa.tzinfo else sa.replace(tzinfo=timezone.utc)
            if aware >= now:
                dated_future.append((aware, r))
        else:
            undated.append(r)
    dated_future.sort(key=lambda x: x[0])
    out = [row for _, row in dated_future]
    for r in undated:
        if len(out) >= limit:
            break
        out.append(r)
    return out[:limit]


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
    eid = int(row["event_id"])
    raw_title = (row.get("title") or "").strip()
    if raw_title:
        display = strip_year_token_from_meet_title(raw_title) or generic_varsity_event_label(eid)
    else:
        display = generic_varsity_event_label(eid)
    return {
        "meet_key": f"VARSITY-{row['event_id']}",
        "name": display[:255],
        "location": row.get("subtitle"),
        "start_date": start.date() if isinstance(start, datetime) else None,
        "end_date": end.date() if isinstance(end, datetime) else None,
        "starts_at": start if isinstance(start, datetime) else None,
        "ends_at": end if isinstance(end, datetime) else None,
        "source": "varsity_tv",
    }


def sync_cheer_mvp_meets_from_varsity(
    db: Session, results_max_items: Optional[int] = None
) -> Dict[str, int]:
    """
    Upsert CheerMvpMeet rows from Varsity schedule + results listing.

    Rows whose Varsity title contains ``REBROADCAST`` (case-insensitive) are omitted.

    ``db`` is a SQLAlchemy Session. Commits once on success.
    Returns counts: inserted, updated, total_merged, skipped_rebroadcast.
    """
    from db.mvp_models import CheerMvpMeet

    schedule = fetch_schedule_events()
    results: List[Dict[str, Any]] = []
    for row in iter_results_events():
        results.append(row)
        if results_max_items is not None and len(results) >= results_max_items:
            break
    merged = merge_events_by_id(schedule, results)
    skipped_rebroadcast = sum(1 for r in merged if varsity_event_title_has_rebroadcast(r))
    merged = [r for r in merged if not varsity_event_title_has_rebroadcast(r)]

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
            for k in (
                "name",
                "location",
                "start_date",
                "end_date",
                "starts_at",
                "ends_at",
                "source",
            ):
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
    return {
        "inserted": inserted,
        "updated": updated,
        "total_merged": len(merged),
        "skipped_rebroadcast": skipped_rebroadcast,
    }


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


# Season year to drop from Varsity meet titles in DB (standalone token, not e.g. ``120268``).
_MEET_TITLE_OMIT_YEAR = 2026


def strip_year_token_from_meet_title(title: str, year: int = _MEET_TITLE_OMIT_YEAR) -> str:
    """
    Remove ``year`` when it appears as its own token (not part of a longer number).
    Collapses whitespace and trims. Varsity titles often embed the season year (e.g. ``2026``).
    """
    if not title or not str(title).strip():
        return ""
    y = str(int(year))
    s = re.sub(rf"(?<!\d){re.escape(y)}(?!\d)", " ", str(title).strip())
    return re.sub(r"\s+", " ", s).strip()


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


def describe_event_hub_results_absence(event_id: int) -> Optional[str]:
    """
    When ``iter_event_hub_result_rows`` yields nothing, Flo often still returns HTTP 200 with a
    ``message`` section (e.g. "Results not found for event … (api.flosports.tv)") instead of
    score tables. Surfaces that text for logs and ops.
    """
    try:
        payload = fetch_event_hub_results_page(event_id, limit=5, offset=0)
    except requests.RequestException:
        return None
    inner = _unwrap_event_hub_payload(payload)
    parts: List[str] = []
    if inner.get("httpStatus") == 404:
        parts.append("event-hub httpStatus=404")
    for sec in inner.get("sections") or []:
        if sec.get("type") != "message":
            continue
        for key in ("subtitle1", "title", "text"):
            v = sec.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
    if not parts:
        return None
    return " — ".join(dict.fromkeys(parts))[:500]


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
        if not sections:
            break
        tables = [s for s in sections if (s.get("id") or "").startswith("id-table")]
        yield from tables
        # ``limit`` applies to total sections in the payload, not to table count. Stopping when
        # ``len(tables) < page_size`` dropped every page after the first whenever Varsity returned
        # fewer than 100 division tables per response (most events), hiding most scores.
        if len(sections) < page_size:
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


def _hub_result_row_dedupe_key(row: Dict[str, Any]) -> tuple[Any, ...]:
    es = row.get("event_score")
    rs = row.get("raw_score")
    return (
        (row.get("division_round") or "").strip(),
        (row.get("program") or "").strip(),
        (row.get("team") or "").strip(),
        row.get("rank"),
        round(float(es), 6) if es is not None else None,
        round(float(rs), 6) if rs is not None else None,
    )


def _nf_hub_score(val: Any) -> Optional[float]:
    if val is None:
        return None
    return round(float(val), 6)


def compute_hub_results_snapshot_hash(rows: List[Dict[str, Any]]) -> str:
    """
    Stable SHA-256 over the full hub results payload (division, team, scores).
    When this matches ``CheerMvpMeet.hub_results_snapshot_hash``, ingest skips
    deleting and re-inserting sessions/performances — published cheer scores do not change.
    """
    canon: List[List[Any]] = []
    for r in rows:
        canon.append(
            [
                (r.get("division_round") or "").strip(),
                (r.get("program") or "").strip(),
                (r.get("team") or "").strip(),
                r.get("rank"),
                _nf_hub_score(r.get("event_score")),
                _nf_hub_score(r.get("raw_score")),
                _nf_hub_score(r.get("performance_score")),
                _nf_hub_score(r.get("deductions")),
            ]
        )
    canon.sort()
    payload = json.dumps(canon, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def compute_hub_result_row_hash(meet_key: str, row: Dict[str, Any]) -> str:
    """
    Stable per-row identity hash for incremental ingest.
    Excludes score/rank so score corrections update the existing row instead of duplicating.
    """
    canon = [
        meet_key,
        (row.get("division_round") or "").strip(),
        (row.get("program") or "").strip(),
        (row.get("team") or "").strip(),
    ]
    payload = json.dumps(canon, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def collect_hub_paginate_facet_strings(
    event_id: int,
    *,
    page_size: int = 100,
    include_unfaceted: bool = True,
) -> List[str]:
    """
    Collect ``mergeParams.facets`` strings from hub table sections whose ``action.style`` is
    ``paginate`` (the site’s “View all” / full table for that division).
    """
    queries: List[Optional[str]] = []
    if include_unfaceted:
        queries.append(None)
    queries.extend(varsity_results_hub_cheer_category_facets())
    queries.extend(varsity_results_hub_dance_category_facets())

    seen: set[str] = set()
    for fac in queries:
        offset = 0
        while True:
            try:
                payload = fetch_event_hub_results_page(
                    event_id, limit=page_size, offset=offset, facets=fac
                )
            except requests.RequestException as exc:
                logger.warning(
                    "Event %s paginate facet discovery skip facet %r offset %s: %s",
                    event_id,
                    fac,
                    offset,
                    exc,
                )
                break
            inner = _unwrap_event_hub_payload(payload)
            sections = inner.get("sections") or []
            if not sections:
                break
            for sec in sections:
                if not (sec.get("id") or "").startswith("id-table"):
                    continue
                act = sec.get("action") or {}
                if act.get("style") != "paginate":
                    continue
                mp = act.get("mergeParams") or {}
                fs = mp.get("facets")
                if isinstance(fs, str) and fs.strip():
                    seen.add(fs.strip())
            if len(sections) < page_size:
                break
            offset += page_size
    return sorted(seen)


def _events_path_segment_from_slug_uri(
    slug_uri: Optional[str], event_id: int
) -> Optional[str]:
    """``/events/14478-…`` segment from hub ``slugUri`` (must start with numeric ``event_id``)."""
    if not slug_uri or not isinstance(slug_uri, str):
        return None
    m = re.search(r"/events/([^/?#]+)", slug_uri.strip())
    if not m:
        return None
    seg = m.group(1).strip()
    prefix = str(int(event_id))
    if not seg.startswith(prefix):
        return None
    return seg


def _view_all_request_proxies() -> Optional[Dict[str, str]]:
    p = (
        os.getenv("CHEER_HUB_VIEW_ALL_HTTPS_PROXY")
        or os.getenv("CHEER_HUB_VIEW_ALL_PROXY")
        or ""
    ).strip()
    if not p:
        return None
    return {"http": p, "https": p}


def _fetch_varsity_view_all_html(
    event_id: int,
    facets_json_str: str,
    user_agent: str,
    *,
    events_path_segment: Optional[str] = None,
) -> str:
    enc = quote(facets_json_str, safe="")
    env_seg = (os.getenv("VARSITY_TV_EVENTS_PATH") or "").strip()
    segment = (
        (events_path_segment or "").strip()
        or env_seg
        or str(int(event_id))
    )
    url = f"{VARSITY_TV_PUBLIC_ORIGIN}/events/{segment}/results/view-all?facets={enc}"
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    proxies = _view_all_request_proxies()
    r = s.get(url, timeout=REQUEST_TIMEOUT, proxies=proxies)
    r.raise_for_status()
    return r.text


def _view_all_primary_text_cell(td: Any) -> str:
    if td is None:
        return ""
    main = td.select_one(".text-truncate.text")
    if main:
        return main.get_text(strip=True)
    return td.get_text(strip=True)


def _view_all_program_team(td: Any) -> tuple[str, str]:
    if td is None:
        return "", ""
    p = td.select_one(".text-truncate.text")
    t = td.select_one(".text-truncate.sub-text")
    prog = p.get_text(strip=True) if p else ""
    team = t.get_text(strip=True) if t else ""
    return prog, team


def _view_all_playing_id(td: Any) -> Optional[str]:
    if td is None:
        return None
    a = td.find("a", href=True)
    if not a:
        return None
    href = a.get("href") or ""
    m = re.search(r"[?&]playing=(\d+)", href)
    return m.group(1) if m else None


def parse_varsity_view_all_results_html(
    html: str, event_id: int
) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Parse Angular results markup from ``/results/view-all`` into the same row dicts as
    ``parse_event_hub_table_section``.
    """
    soup = BeautifulSoup(html, "lxml")
    title: Optional[str] = None
    for h2 in soup.find_all("h2"):
        t = h2.get_text(strip=True)
        if not t:
            continue
        low = t.lower()
        if any(x in low for x in ("prelims", "finals", "semi")):
            title = t
            break
    if not title:
        return None

    cells: Dict[Tuple[int, int], Any] = {}
    for el in soup.select("[data-test]"):
        dt = el.get("data-test") or ""
        m = re.match(r"row-(\d+)-table-cell-(\d+)$", dt)
        if m:
            cells[(int(m.group(1)), int(m.group(2)))] = el

    row_indices = {r for (r, _c) in cells.keys()}
    if not row_indices:
        return None

    rows_out: List[Dict[str, Any]] = []
    for ri in sorted(row_indices):
        required = [(ri, c) for c in range(7)]
        if any(k not in cells for k in required):
            continue
        rank_txt = _view_all_primary_text_cell(cells[(ri, 0)])
        prog, team = _view_all_program_team(cells[(ri, 2)])
        if not prog and not team:
            continue
        rs = _parse_score_float(_view_all_primary_text_cell(cells[(ri, 3)]))
        ded = _parse_score_float(_view_all_primary_text_cell(cells[(ri, 4)]))
        ps = _parse_score_float(_view_all_primary_text_cell(cells[(ri, 5)]))
        es = _parse_score_float(_view_all_primary_text_cell(cells[(ri, 6)]))
        playing = _view_all_playing_id(cells[(ri, 0)]) or _view_all_playing_id(
            cells[(ri, 2)]
        )
        replay_path = None
        a2 = cells[(ri, 2)].find("a", href=True) if cells.get((ri, 2)) else None
        if a2 and a2.get("href"):
            replay_path = a2.get("href")
        rows_out.append(
            {
                "event_id": event_id,
                "division_round": title,
                "rank_label": rank_txt,
                "rank": _parse_rank_int(rank_txt),
                "program": prog,
                "team": team,
                "raw_score": rs,
                "deductions": ded,
                "performance_score": ps,
                "event_score": es,
                "video_playing_id": playing,
                "replay_path": replay_path,
            }
        )
    if not rows_out:
        return None
    return (title, rows_out)


def supplement_hub_rows_with_view_all_html(
    event_id: int,
    api_rows: List[Dict[str, Any]],
    *,
    page_size: int = 100,
    include_unfaceted: bool = True,
    paginate_facet_strs: Optional[List[str]] = None,
    events_path_segment: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Replace hub JSON preview tables with full rows from public ``view-all`` HTML when the HTML
    has strictly more rows for the same division title.
    """
    if os.getenv("CHEER_HUB_VIEW_ALL_HTML", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return api_rows

    by_div: Dict[str, List[Dict[str, Any]]] = {}
    for r in api_rows:
        k = (r.get("division_round") or "").strip()
        by_div.setdefault(k, []).append(r)

    facet_strs = paginate_facet_strs
    if facet_strs is None:
        facet_strs = collect_hub_paginate_facet_strings(
            event_id, page_size=page_size, include_unfaceted=include_unfaceted
        )
    replacements: Dict[str, List[Dict[str, Any]]] = {}
    ua = os.getenv(
        "VARSITY_VIEW_ALL_UA",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )
    delay = float(os.getenv("CHEER_HUB_VIEW_ALL_DELAY_S", "0.12"))

    n_406 = 0
    n_other = 0
    first_other: Optional[str] = None
    for i, fs in enumerate(facet_strs):
        if i > 0 and delay > 0:
            time.sleep(delay)
        try:
            html = _fetch_varsity_view_all_html(
                event_id, fs, ua, events_path_segment=events_path_segment
            )
        except requests.RequestException as exc:
            resp = getattr(exc, "response", None)
            code = getattr(resp, "status_code", None) if resp is not None else None
            if code == 406:
                n_406 += 1
                logger.debug(
                    "Event %s view-all 406 (facets prefix %r)",
                    event_id,
                    fs[:100],
                )
            else:
                n_other += 1
                if first_other is None:
                    first_other = str(exc)[:240]
                logger.debug(
                    "Event %s view-all skip (facets prefix %r): %s",
                    event_id,
                    fs[:100],
                    exc,
                )
            continue
        parsed = parse_varsity_view_all_results_html(html, event_id)
        if not parsed:
            continue
        title, hrows = parsed
        if not title or not hrows:
            continue
        api_n = len(by_div.get(title, []))
        if len(hrows) <= api_n:
            continue
        prev = replacements.get(title)
        if prev is None or len(hrows) > len(prev):
            replacements[title] = hrows

    if not replacements:
        if n_406 and not n_other:
            logger.warning(
                "Event %s: view-all HTML returned HTTP 406 for all %s facet fetches "
                "(Flo often blocks datacenter egress to tv.varsity.com; set "
                "CHEER_HUB_VIEW_ALL_HTTPS_PROXY, or use a runner IP that receives 200). "
                "Hub JSON preview rows were kept.",
                event_id,
                n_406,
            )
        elif n_406 or n_other:
            logger.warning(
                "Event %s: view-all HTML had no expansions (%s×406, %s other); %s",
                event_id,
                n_406,
                n_other,
                first_other or "",
            )
        return api_rows

    kept = [
        r
        for r in api_rows
        if (r.get("division_round") or "").strip() not in replacements
    ]
    for _t, hrows in replacements.items():
        kept.extend(hrows)

    seen: set[tuple[Any, ...]] = set()
    out: List[Dict[str, Any]] = []
    for row in kept:
        key = _hub_result_row_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    # Hub JSON is often a short preview (e.g. 3 rows); log hub→html counts as proof of full grids.
    deltas = sorted(
        (
            (t, len(by_div.get(t, [])), len(hrows))
            for t, hrows in replacements.items()
        ),
        key=lambda x: (x[2] - x[1], x[2]),
        reverse=True,
    )
    delta_str = ", ".join(f"{a}→{h}" for _t, a, h in deltas[:4])
    if len(deltas) > 4:
        delta_str = f"{delta_str}, +{len(deltas) - 4} more"
    logger.info(
        "Event %s: view-all HTML replaced %s division table(s), row counts (hub→html): %s; %s rows after dedupe",
        event_id,
        len(replacements),
        delta_str,
        len(out),
    )
    return out


def varsity_results_hub_cheer_category_facets() -> List[str]:
    """``facets`` query values matching Varsity.tv Results filters (Cheer → category)."""
    cats = (
        "Novice",
        "Rec",
        "Prep",
        "Level 1",
        "Level 2",
        "Level 3",
        "Level 4",
        "Level 5",
        "Level 6",
        "Level 7",
        "CheerABILITIES",
    )
    return [
        json.dumps({"class": "Cheer", "category": c}, separators=(",", ":")) for c in cats
    ]


def varsity_results_hub_dance_category_facets() -> List[str]:
    cats = ("Level 1", "Level 2", "Level 3", "Level 4", "Level 5")
    return [
        json.dumps({"class": "Dance", "category": c}, separators=(",", ":")) for c in cats
    ]


def collect_event_hub_all_result_rows(
    event_id: int,
    *,
    page_size: int = 100,
    include_unfaceted: bool = True,
) -> List[Dict[str, Any]]:
    """
    Merge score rows from the hub default view plus each class/category facet.

    The website (e.g. Level 2 only) passes ``facets``; without it, Flo often returns only a slice
    of divisions. Dedupes overlapping rows across queries.

    JSON tables are often preview-only; see ``supplement_hub_rows_with_view_all_html`` (on by default).
    """
    queries: List[Optional[str]] = []
    if include_unfaceted:
        queries.append(None)
    queries.extend(varsity_results_hub_cheer_category_facets())
    queries.extend(varsity_results_hub_dance_category_facets())

    seen: set[tuple[Any, ...]] = set()
    out: List[Dict[str, Any]] = []
    paginate_facets_seen: set[str] = set()
    events_path_segment: Optional[str] = None
    for fac in queries:
        offset = 0
        while True:
            try:
                payload = fetch_event_hub_results_page(
                    event_id, limit=page_size, offset=offset, facets=fac
                )
            except requests.RequestException as exc:
                logger.warning(
                    "Event %s hub results skip facet %r offset %s: %s",
                    event_id,
                    fac,
                    offset,
                    exc,
                )
                break
            inner = _unwrap_event_hub_payload(payload)
            sections = inner.get("sections") or []
            if not sections:
                break
            for sec in sections:
                sid = sec.get("id") or ""
                if not sid.startswith("id-table"):
                    continue
                act = sec.get("action") or {}
                if act.get("style") == "paginate":
                    mp = act.get("mergeParams") or {}
                    fs = mp.get("facets")
                    if isinstance(fs, str) and fs.strip():
                        paginate_facets_seen.add(fs.strip())
                    an = act.get("analytics") or {}
                    seg = _events_path_segment_from_slug_uri(
                        an.get("slugUri"), event_id
                    )
                    if seg:
                        events_path_segment = seg
                for row in parse_event_hub_table_section(event_id, sec):
                    key = _hub_result_row_dedupe_key(row)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(row)
            if len(sections) < page_size:
                break
            offset += page_size
    logger.info(
        "Event %s: merged %s unique hub result rows from %s facet queries",
        event_id,
        len(out),
        len(queries),
    )
    return supplement_hub_rows_with_view_all_html(
        event_id,
        out,
        page_size=page_size,
        include_unfaceted=include_unfaceted,
        paginate_facet_strs=sorted(paginate_facets_seen),
        events_path_segment=events_path_segment,
    )


def sync_event_results_to_cheer_mvp(
    db: Session,
    event_id: int,
    *,
    meet_name: Optional[str] = None,
    page_size: int = 100,
    facets: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Incrementally sync Cheer MVP sessions/performances for ``VARSITY-{event_id}``.
    Rows are keyed by stable per-result hash (meet + division + program + team):
    existing rows are updated in place; unseen rows are inserted.

    If the results API returns no rows yet (meet not started / no scores posted),
    still upserts ``cheer_mvp_meets`` with name and listing metadata when available.

    When ``facets`` is omitted and ``CHEER_HUB_MERGE_FACETS`` is not disabled, pulls the default
    hub page plus each Varsity ``class``/``category`` facet (Cheer Level 1–7, Dance, etc.) so
    divisions visible on tv.varsity.com (e.g. Level 2) are not skipped.

    Commits once. Returns counts; ``no_result_rows`` is True when scores were empty.
    """
    from db.mvp_models import (
        CheerMvpMeet,
        CheerMvpPerformance,
        CheerMvpSession,
        CheerMvpTeam,
    )

    # Pre-event / unpublished events often return 4xx from ``/event-hub/.../results``.
    # We still want ``cheer_mvp_meets`` upserted; do not fail the whole sync on HTTP errors here.
    rows: List[Dict[str, Any]] = []
    results_hub_error: Optional[str] = None
    merge_facets = os.getenv("CHEER_HUB_MERGE_FACETS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    try:
        if facets is not None:
            rows = list(
                iter_event_hub_result_rows(event_id, page_size=page_size, facets=facets)
            )
        elif merge_facets:
            rows = collect_event_hub_all_result_rows(event_id, page_size=page_size)
        else:
            rows = list(
                iter_event_hub_result_rows(event_id, page_size=page_size, facets=None)
            )
    except requests.RequestException as exc:
        results_hub_error = str(exc)
        logger.warning(
            "Event-hub results fetch failed for event %s (saving meet only): %s",
            event_id,
            exc,
        )

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
    stripped = strip_year_token_from_meet_title(display_name)
    if stripped:
        display_name = stripped[:255]
    elif re.search(rf"(?<!\d){_MEET_TITLE_OMIT_YEAR}(?!\d)", display_name or ""):
        display_name = generic
    if not (display_name or "").strip():
        display_name = generic
    display_name = display_name[:255]

    if varsity_display_name_has_rebroadcast(display_name):
        logger.info(
            "Skip Varsity event %s: rebroadcast in display name %r (no DB changes)",
            event_id,
            display_name,
        )
        return {
            "event_id": event_id,
            "meet_key": meet_key,
            "name": display_name,
            "skipped_rebroadcast": True,
            "sessions": 0,
            "performances": 0,
            "teams_touched": 0,
            "no_result_rows": True,
        }

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
            meet.starts_at = st_at
        if isinstance(en_at, datetime):
            meet.end_date = en_at.date()
            meet.ends_at = en_at
        elif isinstance(st_at, datetime) and meet.end_date is None:
            meet.end_date = st_at.date()

    if not rows:
        db.commit()
        hub_absence = (
            None
            if results_hub_error
            else describe_event_hub_results_absence(event_id)
        )
        if hub_absence:
            logger.warning(
                "Varsity event %s: no score tables ingested — %s. "
                "Schedule/ticker can still list this event; Flo must expose "
                "``/event-hub/<id>/results`` tables for ingest (check event id on the site).",
                event_id,
                hub_absence,
            )
        else:
            logger.info(
                "Varsity event %s: no result rows yet; saved meet %s (%r)",
                event_id,
                meet_key,
                display_name,
            )
        out: Dict[str, Any] = {
            "event_id": event_id,
            "meet_key": meet_key,
            "name": display_name,
            "sessions": 0,
            "performances": 0,
            "teams_touched": 0,
            "no_result_rows": True,
        }
        if results_hub_error:
            out["results_hub_unavailable"] = True
            out["results_hub_error"] = results_hub_error[:500]
        elif hub_absence:
            out["event_hub_no_tables"] = True
            out["event_hub_message"] = hub_absence
        return out

    snapshot_hash = compute_hub_results_snapshot_hash(rows)
    meet.hub_results_snapshot_hash = snapshot_hash

    session_by_label: Dict[str, CheerMvpSession] = {}
    perf_counters: Dict[int, int] = {}

    existing_sessions = (
        db.query(CheerMvpSession)
        .filter(CheerMvpSession.meet_id == meet.id)
        .order_by(CheerMvpSession.display_order.asc(), CheerMvpSession.id.asc())
        .all()
    )
    for s in existing_sessions:
        session_by_label[s.name] = s
        perf_counters[s.id] = 0

    existing_perf_order_rows = (
        db.query(CheerMvpPerformance.session_id, CheerMvpPerformance.display_order)
        .filter(CheerMvpPerformance.meet_id == meet.id)
        .all()
    )
    for sid, order in existing_perf_order_rows:
        nxt = int((order or 0) + 1)
        perf_counters[sid] = max(perf_counters.get(sid, 0), nxt)

    row_hashes = [compute_hub_result_row_hash(meet_key, r) for r in rows]
    existing_perf_by_hash = {
        p.source_row_hash: p
        for p in db.query(CheerMvpPerformance)
        .filter(
            CheerMvpPerformance.meet_id == meet.id,
            CheerMvpPerformance.source_row_hash.in_(row_hashes),
        )
        .all()
        if p.source_row_hash
    }
    legacy_perf_by_identity: Dict[Tuple[str, str, str], CheerMvpPerformance] = {}
    legacy_rows = (
        db.query(CheerMvpPerformance, CheerMvpSession.name, CheerMvpTeam.gym_name, CheerMvpTeam.name)
        .join(CheerMvpSession, CheerMvpSession.id == CheerMvpPerformance.session_id)
        .join(CheerMvpTeam, CheerMvpTeam.id == CheerMvpPerformance.team_id)
        .filter(
            CheerMvpPerformance.meet_id == meet.id,
            CheerMvpPerformance.source_row_hash.is_(None),
            CheerMvpPerformance.is_break.is_(False),
        )
        .all()
    )
    for perf, sess_name, gym_name, team_name in legacy_rows:
        k = (
            (sess_name or "").strip().lower(),
            (gym_name or "").strip().lower(),
            (team_name or "").strip().lower(),
        )
        if k not in legacy_perf_by_identity:
            legacy_perf_by_identity[k] = perf

    inserted_n = 0
    updated_n = 0
    skipped_n = 0

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
            perf_counters[s.id] = 0
        return session_by_label[label]

    for r, row_hash in zip(rows, row_hashes):
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

        es = r.get("event_score")
        rs = r.get("raw_score")
        ps = r.get("performance_score")
        final_score = float(es) if es is not None else None
        raw_score = float(rs) if rs is not None else None
        perf_score = float(ps) if ps is not None else None
        rank = r.get("rank")
        deductions = r.get("deductions")

        existing_perf = existing_perf_by_hash.get(row_hash)
        if existing_perf is None:
            legacy_key = (
                label.strip().lower(),
                program.strip().lower(),
                team_nm.strip().lower(),
            )
            existing_perf = legacy_perf_by_identity.get(legacy_key)
            if existing_perf is not None and existing_perf.source_row_hash is None:
                existing_perf.source_row_hash = row_hash
                existing_perf_by_hash[row_hash] = existing_perf
        if existing_perf is not None:
            changed = False
            if existing_perf.session_id != sess.id:
                existing_perf.session_id = sess.id
                changed = True
            if existing_perf.team_id != team.id:
                existing_perf.team_id = team.id
                changed = True
            if existing_perf.round != ((r.get("division_round") or "")[:64] or None):
                existing_perf.round = (r.get("division_round") or "")[:64] or None
                changed = True
            if existing_perf.final_score != final_score:
                existing_perf.final_score = final_score
                changed = True
            if existing_perf.raw_score != raw_score:
                existing_perf.raw_score = raw_score
                changed = True
            if existing_perf.performance_score != perf_score:
                existing_perf.performance_score = perf_score
                changed = True
            if existing_perf.rank != rank:
                existing_perf.rank = rank
                changed = True
            if existing_perf.deductions != deductions:
                existing_perf.deductions = deductions
                changed = True
            if changed:
                updated_n += 1
            else:
                skipped_n += 1
            continue

        sid = sess.id
        next_order = perf_counters.get(sid, 0)
        perf_counters[sid] = next_order + 1
        perf = CheerMvpPerformance(
            meet_id=meet.id,
            session_id=sess.id,
            team_id=team.id,
            is_break=False,
            scheduled_time=None,
            status="final",
            display_order=next_order,
            round=(r.get("division_round") or "")[:64] or None,
            final_score=final_score,
            raw_score=raw_score,
            performance_score=perf_score,
            rank=rank,
            deductions=deductions,
            source_row_hash=row_hash,
        )
        db.add(perf)
        existing_perf_by_hash[row_hash] = perf
        inserted_n += 1

    db.commit()
    return {
        "event_id": event_id,
        "meet_key": meet_key,
        "sessions": len(session_by_label),
        "performances": inserted_n + updated_n,
        "teams_touched": inserted_n + updated_n,
        "inserted_performances": inserted_n,
        "updated_performances": updated_n,
        "skipped_unchanged_performances": skipped_n,
        "hub_results_snapshot_hash": snapshot_hash,
    }
