"""
MeetScoresOnline (MSO) Scraper — Playwright-based

MSO loads all scores via JavaScript after page load.
requests/BeautifulSoup only sees template placeholders like #{fullname}.
Playwright runs a real browser, dismisses the paywall overlay, iterates
all session tabs, and reads the fully rendered score tables.
"""

import logging
import re
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
import hashlib
from collections import defaultdict

logger = logging.getLogger(__name__)

MSO_BASE = "https://www.meetscoresonline.com"
PAGE_LOAD_TIMEOUT = 20000
DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

# When enabled, only scrape session-picker items that match "today" in the given timezone.
MSO_ONLY_TODAY_SESSIONS = os.getenv("MSO_ONLY_TODAY_SESSIONS", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MSO_TZ = os.getenv("MSO_TZ", "America/New_York").strip() or "America/New_York"
MSO_MOBILE_EMULATION = os.getenv("MSO_MOBILE_EMULATION", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def get_playwright_context_kwargs() -> Dict:
    """Build Playwright context config for normal desktop scraping."""
    # Even if MSO_MOBILE_EMULATION is set, we keep the scraper in its
    # original desktop mode for lightweight ingest.
    return {"user_agent": DEFAULT_UA}


def _harden_playwright_context(context) -> None:
    """Reduce obvious automation fingerprints."""
    try:
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        context.add_init_script(
            "window.chrome = window.chrome || { runtime: {} };"
        )
    except Exception:
        pass


def _today_in_mso_tz() -> str:
    """
    Return today's date in MSO_TZ as M/D/YYYY (no zero padding).
    """
    try:
        from zoneinfo import ZoneInfo  # py3.9+

        d = datetime.now(ZoneInfo(MSO_TZ)).date()
    except Exception:
        d = datetime.utcnow().date()
    return f"{d.month}/{d.day}/{d.year}"


_MDY_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _extract_mdy(text: str) -> Optional[str]:
    m = _MDY_RE.search(text or "")
    if not m:
        return None
    mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
    try:
        return f"{int(mm)}/{int(dd)}/{int(yyyy)}"
    except Exception:
        return None


def _session_picker_indices_for_today(item_texts: list[str], today_mdy: str) -> list[int]:
    """
    Date-based MSO meets: a row like "Today (Fri) 3/20/2026" sets the active day; following
    rows are sessions ("01 - Level 6 ...") with NO date in the text. A naive filter that only
    keeps lines containing M/D/YYYY misses those sessions → 0 rows scraped.
    Carry forward the most recent date header and include every item under today's date.
    """
    indices: list[int] = []
    current_mdy: Optional[str] = None
    for idx, t in enumerate(item_texts):
        m = _extract_mdy(t)
        if m:
            current_mdy = m
        if current_mdy == today_mdy:
            indices.append(idx)
    return indices


# JavaScript to remove MSO's "All Access Pass" paywall overlay
DISMISS_OVERLAY_JS = """
    ['showmessage_overlay', 'showmessage', 'IGCOfferModal'].forEach(id => {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    ['popup_block', 'igc-offer', 'IGCOffer', 'offer-modal'].forEach(id => {
        var el = document.getElementById(id);
        if (el) {
            el.style.display = 'none';
            el.style.pointerEvents = 'none';
            if (el.parentNode) { try { el.parentNode.removeChild(el); } catch(e) {} }
        }
    });
    document.querySelectorAll(
        '#popup_block, [name="igc-offer"], [class*="igc"], [class*="offer"], [id*="offer"]'
    ).forEach(e => {
        e.style.display = 'none';
        e.style.pointerEvents = 'none';
        try { e.remove(); } catch(err) {}
    });
    document.querySelectorAll(
        '.modal-backdrop, .modal.show, [id*="overlay"], [id*="modal"]'
    ).forEach(e => e.style.display = 'none');
    document.body.style.overflow = 'auto';
"""

def audit_duplicate_hashes(rows):
    """
    Inspect all rows and find duplicates by record_hash.
    Prints detailed info for each duplicate hash.
    """
    from collections import defaultdict
    hash_map = defaultdict(list)

    for i, row in enumerate(rows):
        # Recompute hash in case it wasn't set correctly
        key = (
            str(row.get("athlete_name", "")).strip().lower() + "|" +
            str(row.get("meet_id", "")) + "|" +
            str(row.get("session", "")) + "|" +
            str(row.get("event", "")) + "|" +
            str(row.get("score", "")) + "|" +
            str(row.get("division", "")) + "|" +
            str(row.get("level", ""))
        )
        record_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        row["_audit_key"] = key
        row["_audit_hash"] = record_hash
        hash_map[record_hash].append((i, row))

    duplicates = {h: v for h, v in hash_map.items() if len(v) > 1}

    if not duplicates:
        print("No duplicate hashes detected.")
        return

    print(f"Found {len(duplicates)} duplicate hashes!\n")
    for h, entries in duplicates.items():
        print(f"Duplicate hash: {h}")
        for idx, row in entries:
            print(f" Index {idx}: athlete={row.get('athlete_name')}, meet={row.get('meet_id')}, "
                  f"session={row.get('session')}, event={row.get('event')}, score={row.get('score')}, "
                  f"division={row.get('division')}, level={row.get('level')}")
            print(f"  Key used for hash: {row['_audit_key']}")
        print("-" * 80)



def make_record_hash(row: dict) -> str:
    key = (
        str(row.get("athlete_name", "")).strip().lower() +
        "|" + str(row.get("meet_id", "")) +
        "|" + str(row.get("session", "")) +
        "|" + str(row.get("event", "")) +
        "|" + str(row.get("score", "")) +
        "|" + str(row.get("division", "")) +
        "|" + str(row.get("level", ""))
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def deduplicate_rows(rows: list[dict]) -> list[dict]:
    seen_hashes = set()
    unique_rows = []

    for row in rows:
        row_hash = row.get("record_hash")
        if not row_hash:
            row_hash = make_record_hash(row)
            row["record_hash"] = row_hash

        if row_hash not in seen_hashes:
            unique_rows.append(row)
            seen_hashes.add(row_hash)

    return unique_rows

from typing import List, Dict

def _result_urls_for_mso(context, mso_url: str) -> List[str]:
    # If caller already passed a direct results URL, don't waste time
    # opening the meet landing page to resolve sub-links.
    if ("/R" in mso_url) or ("/Results/" in mso_url):
        return [mso_url]
    return _resolve_result_urls(context, mso_url) or [mso_url]


def scrape_mso_meet_with_context(context, mso_url: str) -> List[Dict]:
    """
    Scrape all result rows from a MSO meet page using Playwright, returning
    only unique rows by record_hash.

    Args:
        mso_url: Full URL to the meet page or results page

    Returns:
        List of unique raw score dicts ready for DB insertion
    """
    logger.info("Scraping MSO meet: %s", mso_url)
    rows: List[Dict] = []
    meet_id = _extract_meet_id_from_url(mso_url)
    result_urls = _result_urls_for_mso(context, mso_url)
    for result_url in result_urls:
        page_rows = _scrape_result_page(context, result_url, meet_id)
        rows.extend(page_rows)
        logger.info("  %s → %d rows scraped", result_url, len(page_rows))

    # Deduplicate rows by record_hash
    unique_rows: List[Dict] = []
    seen_hashes = set()
    duplicate_count = 0

    for row in rows:
        record_hash = row.get("record_hash")
        if record_hash in seen_hashes:
            duplicate_count += 1
        else:
            unique_rows.append(row)
            seen_hashes.add(record_hash)

    if duplicate_count > 0:
        logger.warning("Skipped %d duplicate rows based on record_hash", duplicate_count)

    logger.info(
        "MSO scraped %d total rows → %d unique rows for insertion from %s",
        len(rows), len(unique_rows), mso_url
    )

    return unique_rows


def scrape_mso_meet(mso_url: str) -> List[Dict]:
    """
    Backwards-compatible wrapper that owns the Playwright lifecycle.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed.")
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**get_playwright_context_kwargs())
        try:
            return scrape_mso_meet_with_context(context, mso_url)
        finally:
            browser.close()


def fingerprint_mso_results_page_with_context(context, mso_url: str) -> Optional[str]:
    """
    Compute a lightweight fingerprint for an MSO results page using an existing
    Playwright context (so callers can reuse the same browser for scrape+fingerprint).
    """
    meet_id = _extract_meet_id_from_url(mso_url)

    def _fingerprint_one(url: str) -> str:
        from bs4 import BeautifulSoup

        page = context.new_page()
        # Fingerprinting should be cheap; avoid waiting for full network idle.
        page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        _dismiss_overlay(page)

        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('#{fullname}')",
                timeout=PAGE_LOAD_TIMEOUT,
            )
        except Exception:
            pass

        # Align fingerprinting with scraping: for date-based meets, select today's date item
        # so we don't treat changes on past days as "changed".
        if MSO_ONLY_TODAY_SESSIONS:
            try:
                _dismiss_overlay(page)
                _open_session_dropdown(page, timeout_ms=2500)
                page.wait_for_timeout(300)
                picker_items = page.query_selector_all(".session-picker-item")
                item_texts = []
                for item in picker_items:
                    try:
                        item_texts.append((item.inner_text() or "").strip())
                    except Exception:
                        item_texts.append("")

                today_mdy = _today_in_mso_tz()
                has_any_dates = any(_extract_mdy(t) for t in item_texts)
                if has_any_dates:
                    idxs = _session_picker_indices_for_today(item_texts, today_mdy)
                    if not idxs:
                        idxs = list(range(len(picker_items)))
                    chosen = idxs[-1]
                    for cand in reversed(idxs):
                        tx = item_texts[cand]
                        if re.search(r"\d\s*-\s*", tx) or "level" in tx.lower():
                            chosen = cand
                            break
                    try:
                        target = picker_items[chosen]
                        _dismiss_overlay(page)
                        target.click(timeout=2500)
                    except Exception:
                        _dismiss_overlay(page)
                        page.evaluate("el => el.click()", picker_items[chosen])
                    page.wait_for_timeout(600)
                    _dismiss_overlay(page)
            except Exception:
                pass

        html = page.content()
        page.close()

        soup = BeautifulSoup(html, "lxml")
        tables = soup.select("table")
        if tables:
            payload = "\n".join(t.get_text(" ", strip=True) for t in tables)
        else:
            payload = soup.get_text(" ", strip=True)

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    result_urls = _result_urls_for_mso(context, mso_url)
    parts: List[str] = []
    for url in result_urls:
        parts.append(_fingerprint_one(url))

    combined = f"{meet_id}|" + "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def fingerprint_mso_results_page(mso_url: str) -> Optional[str]:
    """
    Compute a lightweight fingerprint for an MSO results page.

    This is used for change detection so scheduled jobs can skip the expensive
    normalize/save pipeline when the upstream page hasn't changed.

    Returns:
        sha256 hex digest string, or None if fingerprinting fails.
    """
    logger.info("Fingerprinting MSO results: %s", mso_url)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(**get_playwright_context_kwargs())
            try:
                return fingerprint_mso_results_page_with_context(context, mso_url)
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("Could not fingerprint %s: %s", mso_url, exc)
        return None


def _dismiss_overlay(page) -> None:
    """Remove MSO's paywall/modal overlay so the page is fully interactive."""
    try:
        page.evaluate(DISMISS_OVERLAY_JS)
        # Force-clear any fixed elements still intercepting clicks.
        page.evaluate(
            "() => { document.querySelectorAll('[style*=\"position: fixed\"], [style*=\"z-index\"]').forEach(el => {"
            "const id=(el.id||'').toLowerCase(); const cls=(el.className||'').toString().toLowerCase();"
            "if (id.includes('offer') || id.includes('popup') || cls.includes('offer') || cls.includes('popup')) {"
            "el.style.pointerEvents='none'; el.style.display='none'; } }); }"
        )
        page.wait_for_timeout(400)
    except Exception:
        pass


def _open_session_dropdown(page, timeout_ms: int = 5000) -> None:
    """Open the MSO session dropdown with resilient click fallbacks."""
    _dismiss_overlay(page)
    try:
        page.click("a.session.btn", timeout=timeout_ms)
        return
    except Exception:
        pass
    _dismiss_overlay(page)
    try:
        page.locator("a.session.btn").first.click(timeout=timeout_ms, force=True)
        return
    except Exception:
        pass
    _dismiss_overlay(page)
    # Final fallback: JS click bypasses pointer interception.
    page.evaluate(
        "() => { const el = document.querySelector('a.session.btn'); if (el) el.click(); }"
    )


def _resolve_result_urls(context, slug_url: str) -> List[str]:
    """
    Open the meet event page and collect links to /Results/<id> sub-pages.
    """
    if "/Results/" in slug_url:
        return []

    try:
        page = context.new_page()
        page.goto(slug_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        _dismiss_overlay(page)

        links = page.eval_on_selector_all(
            "a[href*='/Results/']",
            "els => els.map(e => e.href)"
        )
        page.close()

        seen = set()
        result_urls = []
        for link in links:
            m = re.search(r"/Results/(\d+)", link)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                result_urls.append(f"{MSO_BASE}/Results/{m.group(1)}")

        return result_urls

    except Exception as exc:
        logger.warning("Could not resolve result URLs from %s: %s", slug_url, exc)
        return []


def _scrape_result_page(context, result_url: str, meet_id: str) -> List[Dict]:
    """
    Open a /Results/<id> page, dismiss the overlay, iterate all session tabs,
    and collect every score row.
    """
    rows = []
    seen_keys = set()
    heartbeat_every_s = 30.0
    started_at = time.monotonic()
    last_heartbeat_at = started_at

    def heartbeat(stage: str):
        nonlocal last_heartbeat_at
        now = time.monotonic()
        if (now - last_heartbeat_at) < heartbeat_every_s:
            return
        elapsed = int(now - started_at)
        logger.info(
            "  scrape heartbeat (%ss): %s | rows=%d | unique_keys=%d",
            elapsed,
            stage,
            len(rows),
            len(seen_keys),
        )
        last_heartbeat_at = now

    logged_table_shape = False

    def collect_rows(pg):
        nonlocal logged_table_shape
        from bs4 import BeautifulSoup
        html = pg.content()
        soup = BeautifulSoup(html, "lxml")
        found = []
        tables = soup.select("table")
        if not logged_table_shape:
            logger.info("  HTML scan: found %d tables", len(tables))
            if tables:
                try:
                    first_rows = []
                    for t in tables[:3]:
                        tr = t.select_one("tr")
                        first_rows.append(tr.get_text(" ", strip=True)[:180] if tr else "")
                    logger.info("  HTML scan: first-row previews: %s", first_rows)
                except Exception:
                    pass
            logged_table_shape = True
        for table in tables:
            for row in _parse_result_table(table, meet_id):
                key = f"{row.get('athlete_name')}|{row.get('level')}|{row.get('event')}|{row.get('score')}"
                if key not in seen_keys and row.get('athlete_name'):
                    seen_keys.add(key)
                    found.append(row)
        return found

    try:
        page = context.new_page()
        page.goto(result_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")

        # *** Dismiss the paywall overlay — this was blocking all session clicks ***
        _dismiss_overlay(page)

        # Wait for scores to render
        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('#{fullname}')",
                timeout=PAGE_LOAD_TIMEOUT,
            )
        except Exception:
            pass

        # Strategy 1: Try "Combined" first (works when sessions are simple A01, B02, etc.)
        combined_rows = []
        try:
            _dismiss_overlay(page)
            _open_session_dropdown(page, timeout_ms=5000)
            page.wait_for_timeout(800)

            # Click the "Combined" option in the session picker
            page.click('.session-picker-item:has-text("Combined")', timeout=5000)
            page.wait_for_timeout(3000)
            _dismiss_overlay(page)
            combined_rows = collect_rows(page)
            logger.info("  Combined view: %d rows", len(combined_rows))
        except Exception as exc:
            logger.debug("  Could not select Combined session: %s", exc)

        rows.extend(combined_rows)

        # Strategy 2: If Combined failed or returned few rows, iterate through Session tabs
        # Some meets use date-based sessions (Saturday 1/17 -> sub-sessions) instead of Combined
        # Session tabs appear as "Session 01 (58)", "Session 02 (42)", etc. in the nav bar
        # IMPORTANT: Exclude a.session.btn - that's the dropdown, not a tab
        session_tab_selectors = []
        try:
            all_links = page.query_selector_all('a, [role="tab"], .nav-link, [class*="session"]')
            for el in all_links:
                try:
                    # Skip the session dropdown button (a.session.btn opens the picker, not a tab)
                    cls = el.get_attribute("class") or ""
                    if "session" in cls and "btn" in cls:
                        continue
                    text = (el.inner_text() or "").strip()
                    # Match "Session 01 (58)" or "Session 02 (42)" - must have count in parens
                    if re.search(r'Session\s*0?\d+\s*\(\d+\)', text, re.IGNORECASE):
                        session_tab_selectors.append(el)
                except Exception:
                    pass
        except Exception:
            pass

        if session_tab_selectors and len(combined_rows) < 30:
            logger.info("  Iterating through %d session tabs (Combined had %d rows)", 
                       len(session_tab_selectors), len(combined_rows))
            for i, tab in enumerate(session_tab_selectors):
                heartbeat(f"session-tab loop {i + 1}/{len(session_tab_selectors)}")
                try:
                    _dismiss_overlay(page)
                    tab.click(timeout=3000)
                    page.wait_for_timeout(2000)  # Wait for scores to load
                    _dismiss_overlay(page)
                    tab_rows = collect_rows(page)
                    if tab_rows:
                        logger.info("  Session tab %d: %d rows", i + 1, len(tab_rows))
                        rows.extend(tab_rows)
                except Exception as exc:
                    logger.debug("  Session tab %d failed: %s", i + 1, exc)

        # Strategy 3: If still few rows, iterate through each session-picker-item in dropdown
        # Handles date-based structure (Saturday 1/17 -> sub-sessions like "01 - L6N/7N 6:50 PM")
        # This is critical when Combined doesn't exist - API scraper often finds 5+ items here
        if len(rows) < 30:
            try:
                _dismiss_overlay(page)
                _open_session_dropdown(page, timeout_ms=5000)
                page.wait_for_timeout(1500)
                picker_items = page.query_selector_all('.session-picker-item')
                logger.info("  Found %d session picker items to iterate", len(picker_items))
                # Collect session item text/identity first, then click each one
                # (dropdown closes after each click, so we re-open it each time)
                item_texts = []
                for item in picker_items:
                    try:
                        item_texts.append((item.inner_text() or "").strip())
                    except Exception:
                        item_texts.append("")

                # Optional optimization for live polling: only scrape sessions for today's date.
                # Date-based meets show items like "Saturday 3/14/2026" / "Sunday 3/15/2026".
                if MSO_ONLY_TODAY_SESSIONS:
                    today_mdy = _today_in_mso_tz()
                    has_any_dates = any(_extract_mdy(t) for t in item_texts)
                    if has_any_dates:
                        indices_to_scrape = _session_picker_indices_for_today(item_texts, today_mdy)
                        logger.info(
                            "  Today-only sessions (%s): %d picker items (date + sessions under that day)",
                            today_mdy,
                            len(indices_to_scrape),
                        )
                        if not indices_to_scrape:
                            logger.info(
                                "  No items under today's date header; scraping all %d picker items",
                                len(item_texts),
                            )
                            indices_to_scrape = list(range(len(item_texts)))
                    else:
                        indices_to_scrape = list(range(len(item_texts)))
                else:
                    indices_to_scrape = list(range(len(item_texts)))

                for i in indices_to_scrape:
                    text = item_texts[i]
                    heartbeat(f"session-picker loop {i + 1}/{len(indices_to_scrape)}")
                    if 'combined' in text.lower():
                        continue
                    try:
                        # Re-open the dropdown before each click (it closes after each selection)
                        _dismiss_overlay(page)
                        _open_session_dropdown(page, timeout_ms=5000)
                        page.wait_for_timeout(800)

                        # Re-query items after re-opening the dropdown
                        fresh_items = page.query_selector_all('.session-picker-item')
                        if i >= len(fresh_items):
                            logger.warning("  Session picker item %d not found after re-open", i + 1)
                            continue
                        target = fresh_items[i]

                        _dismiss_overlay(page)
                        try:
                            target.click(timeout=5000)
                        except Exception:
                            _dismiss_overlay(page)
                            page.evaluate("el => el.click()", target)

                        page.wait_for_timeout(3000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception:
                            pass
                        _dismiss_overlay(page)
                        item_rows = collect_rows(page)
                        if item_rows:
                            logger.info("  Session picker item %d (%s): %d rows", i + 1, text[:50], len(item_rows))
                            rows.extend(item_rows)
                        else:
                            logger.debug("  Session picker item %d (%s): 0 rows", i + 1, text[:50])
                    except Exception as exc:
                        logger.warning("  Session picker item %d (%s) failed: %s", i + 1, text[:40], exc)
            except Exception as exc:
                logger.warning("  Could not iterate session picker items: %s", exc)

        page.close()
        elapsed = int(time.monotonic() - started_at)
        logger.info("  scrape complete (%ss): %d rows", elapsed, len(rows))

    except Exception as exc:
        logger.error("Playwright failed on %s: %s", result_url, exc)

    return rows


def _parse_result_table(table, meet_id: str) -> List[Dict]:
    """Parse a single rendered result <table>."""
    rows = []
    headers = []
    header_like_words = (
        "athlete",
        "gymnast",
        "name",
        "gym",
        "club",
        "team",
        "vault",
        "bars",
        "beam",
        "floor",
        "aa",
        "level",
        "lvl",
        "division",
        "div",
        "session",
        "sess",
    )

    for tr in table.select("tr"):
        # Skip header rows
        if tr.select("th"):
            cells = [td.get_text(strip=True) for td in tr.select("th, td")]
            headers = [_normalize_header(c) for c in cells]
            continue

        # Some MSO tables use first <td> row as header (no <th> tags).
        if not headers:
            first_cells = [td.get_text(strip=True) for td in tr.select("td")]
            normalized_first = [_normalize_header(c) for c in first_cells]
            if normalized_first and any(
                any(word in h for word in header_like_words) for h in normalized_first
            ):
                headers = normalized_first
                continue
        
        # Skip template rows
        cells_text = [td.get_text(strip=True) for td in tr.select("td")]
        if any("#{" in c for c in cells_text):
            continue
        
        if not headers:
            continue

        # Get all td elements (not just text) to extract HTML attributes
        td_elements = tr.select("td")
        if not td_elements:
            continue

        # Build row dict from text content (for backward compatibility)
        row_dict = dict(zip(headers, cells_text))
        
        # Extract placement data from HTML structure
        # Look for <td> elements with class containing "place-" or "event-"
        for td in td_elements:
            classes = td.get("class", [])
            class_str = " ".join(classes) if classes else ""
            
            # Extract place from class name (e.g., "place-1", "place-3")
            place_match = re.search(r"place-(\d+)", class_str)
            place_from_class = None
            if place_match:
                place_from_class = int(place_match.group(1))
            
            # Extract place from <span class="small place"> or similar
            place_span = td.select_one('span.small.place, span.small-place, .small.place')
            place_from_span = None
            if place_span:
                place_text = place_span.get_text(strip=True)
                # Handle ties like "1T" -> extract "1"
                # The "T" suffix indicates a tie, but we store just the numeric placement
                place_match = re.match(r"(\d+)", place_text)
                if place_match:
                    place_from_span = int(place_match.group(1))
            
            # Use span text if available, otherwise use class
            place_value = place_from_span or place_from_class
            
            # Determine which event this td represents
            event_match = re.search(r"event-(\d+|AA)", class_str)
            if event_match:
                event_code = event_match.group(1)
                # Map event codes to our field names
                event_map = {
                    "1": "vault",
                    "2": "bars", 
                    "3": "beam",
                    "4": "floor",
                    "AA": "aa"
                }
                field_name = event_map.get(event_code)
                if field_name:
                    if field_name == "aa":
                        row_dict["AAPlace"] = place_value
                    else:
                        row_dict[f"{field_name}_place"] = place_value
        
        parsed_rows = _extract_score_row(row_dict, meet_id)
        if parsed_rows:
            rows.extend(parsed_rows)

    return rows


def _extract_score_row(row: Dict, meet_id: str) -> List[Dict]:
    athlete = (
        row.get("athlete") or row.get("gymnast")
        or row.get("name") or row.get("athlete_name") or ""
    ).strip()
    gym = (
        row.get("gym")
        or row.get("gym_name")
        or row.get("club")
        or row.get("club_name")
        or row.get("team")
        or ""
    ).strip()
    if not athlete or len(athlete) < 3 or athlete.lower() in ("totals", "total", "team"):
        return []
    if not gym:
        gym = "Unknown Gym"

    vault  = _decode_mso_score(row.get("vault", ""))
    bars   = _decode_mso_score(row.get("bars", "") or row.get("uneven_bars", ""))
    beam   = _decode_mso_score(row.get("beam", ""))
    floor  = _decode_mso_score(row.get("floor", "") or row.get("floor_exercise", ""))
    aa_score = round(sum([s for s in [vault, bars, beam, floor] if s is not None]), 3)

    level_raw = row.get("lvl") or row.get("level") or ""
    div_raw   = row.get("div") or row.get("division") or ""
    sess_raw  = row.get("sess") or row.get("session") or ""

    # Extract place values for AA and individual events
    # First try values extracted from HTML structure (AAPlace, vault_place, etc.)
    # Then fall back to various column name variations
    aa_place = _normalize_place(
        row.get("AAPlace") or row.get("aa_place") or row.get("place") or row.get("aa_place_")
    )
    
    # Individual event places - HTML scraper now extracts these as vault_place, bars_place, etc.
    vault_place = _normalize_place(
        row.get("vault_place") or row.get("VTPlace") or row.get("vt_place") or 
        row.get("VT_Place") or row.get("Vault_Place")
    )
    bars_place = _normalize_place(
        row.get("bars_place") or row.get("UBPlace") or row.get("ub_place") or 
        row.get("UB_Place") or row.get("Bars_Place") or row.get("Uneven_Bars_Place")
    )
    beam_place = _normalize_place(
        row.get("beam_place") or row.get("BBPlace") or row.get("bb_place") or 
        row.get("BB_Place") or row.get("Beam_Place") or row.get("Balance_Beam_Place")
    )
    floor_place = _normalize_place(
        row.get("floor_place") or row.get("FXPlace") or row.get("fx_place") or 
        row.get("FX_Place") or row.get("Floor_Place") or row.get("Floor_Exercise_Place")
    )
    
    # Debug: log place values for first athlete
    if not hasattr(_extract_score_row, '_debug_logged'):
        logger.info("HTML Scraper extracted places for first athlete: AA=%s, vault=%s, bars=%s, beam=%s, floor=%s",
                   aa_place, vault_place, bars_place, beam_place, floor_place)
        logger.info("HTML Scraper available row keys: %s", list(row.keys()))
        logger.info("HTML Scraper raw place values from row: AAPlace=%s, vault_place=%s, bars_place=%s, beam_place=%s, floor_place=%s",
                   row.get("AAPlace"), row.get("vault_place"), row.get("bars_place"), 
                   row.get("beam_place"), row.get("floor_place"))
        _extract_score_row._debug_logged = True

    # Return raw format (one row per athlete) - let normalizer expand into individual events
    # This matches what normalize_mso_record expects: vault, bars, beam, floor fields
    result_row = {
        "athlete_name": athlete,
        "gym": gym,
        "level": str(level_raw).strip() or None,
        "division": str(div_raw).strip() or None,
        "session": str(sess_raw).strip() or None,
        "score": aa_score,  # AA score
        "place": aa_place,  # AA place
        "vault": vault,
        "vault_place": vault_place,
        "bars": bars,
        "bars_place": bars_place,
        "beam": beam,
        "beam_place": beam_place,
        "floor": floor,
        "floor_place": floor_place,
        "meet_id": meet_id,
        "source": "mso",
        "raw_row": row,
    }

    # Compute a deduplication key (athlete + gym + level + division + session)
    # This prevents duplicate rows when same athlete appears in multiple tables
    key = (
        result_row["athlete_name"].lower() + "|" +
        str(result_row["meet_id"]) + "|" +
        str(result_row["session"]) + "|" +
        str(result_row["division"]) + "|" +
        str(result_row["level"])
    )
    result_row["record_hash"] = hashlib.sha256(key.encode("utf-8")).hexdigest()

    return [result_row]  # Return single row, normalizer will expand

def _normalize_place(raw_place) -> Optional[int]:
    """
    Convert raw MSO place (e.g., '1', '3T', 1, '') to integer or None.
    
    Handles ties by extracting the numeric part:
    - "3T" -> 3 (tied for 3rd place)
    - "1T" -> 1 (tied for 1st place)
    - "5" -> 5 (no tie)
    
    The "T" suffix indicates a tie, but we store just the numeric placement
    since multiple athletes can share the same place value.
    """
    if raw_place is None:
        return None
    # If already an integer, return it
    if isinstance(raw_place, int):
        return raw_place
    # Convert string to integer, handling ties like "3T" -> 3
    if not str(raw_place).strip():
        return None
    # Keep only leading digits (strips "T" suffix from ties)
    m = re.match(r"(\d+)", str(raw_place).strip())
    if m:
        return int(m.group(1))
    return None

def _decode_mso_score(raw: str) -> Optional[float]:
    """
    Decode MSO score cells.

    Some pages render plain decimals (e.g. "9.500"); others use encoded digits-only
    blobs (last 4 digits rotated: 9.500 → '5009').
    """
    if not raw:
        return None
    s = str(raw).strip()
    # Plain decimal (common on newer / simplified MSO tables)
    plain = re.search(r"\b(\d{1,2}\.\d{1,4})\b", s)
    if plain:
        try:
            val = float(plain.group(1))
            if 0.0 <= val <= 10.0:
                return round(val, 4)
        except ValueError:
            pass
    # Whole-number scores sometimes appear without decimals
    whole = re.fullmatch(r"(\d{1,2})", re.sub(r"\s+", "", s))
    if whole:
        try:
            val = float(whole.group(1))
            if 0.0 <= val <= 10.0:
                return val
        except ValueError:
            pass

    clean = re.sub(r"[^0-9]", "", s)
    if len(clean) < 4:
        return None
    score_encoded = clean[-4:]
    score_str = score_encoded[-1] + score_encoded[:-1]
    try:
        val = int(score_str) / 1000.0
        if 0.0 <= val <= 10.0:
            return val
        return None
    except ValueError:
        return None


def _decode_mso_place(aa_raw: str) -> Optional[int]:
    """Extract place from MSO encoded AA value prefix."""
    clean = re.sub(r'[^0-9]', '', str(aa_raw))
    if len(clean) <= 4:
        return None
    prefix = clean[:-4]
    try:
        return int(prefix) if prefix else None
    except ValueError:
        return None


def _normalize_header(header: str) -> str:
    return (
        header.lower().strip()
        .replace(" ", "_").replace("-", "_")
        .replace("#", "place").replace("/", "_")
    )


def _extract_meet_id_from_url(url: str) -> str:
    """Extract meet ID from /Results/36321, /R36426, or slug URLs."""
    match = re.search(r"/Results/(\d+)", url)
    if match:
        return f"MSO-{match.group(1)}"
    match = re.search(r"/R(\d+)", url, re.IGNORECASE)
    if match:
        return f"MSO-{match.group(1)}"
    m = re.search(r"meetscoresonline\.com/(.+)$", url)
    return f"MSO-{m.group(1)}" if m else "MSO-UNKNOWN"
