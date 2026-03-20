"""
MeetScoresOnline (MSO) API Scraper — JSON Endpoint

Uses the MSO JSON API endpoint to fetch scores with placement data.
This is more reliable than HTML scraping and includes placement information.

API Endpoint: Ajax.Projects.Json.msoMeet.aspx
Query Parameters:
  - LookupIndex: "1"
  - p_meetid: meet ID (numeric, e.g., "36233")
  - p_scoresid: "" (empty)
  - p_eventid: "" (empty)
  - p_session: session code (e.g., "B03")
  - p_division: "" (empty for all divisions)
  - limit: 5000
"""

import logging
import re
import html
import os
from typing import Dict, List, Optional
import requests
import json

logger = logging.getLogger(__name__)

MSO_BASE = "https://www.meetscoresonline.com"
# MSO's endpoint naming seems to vary slightly between deployments/clients:
# - Ajax.Projects.Json.msoMeet.aspx
# - Ajax.ProjectsJson.msoMeet.aspx
MSO_API_ENDPOINTS = [
    f"{MSO_BASE}/Ajax.Projects.Json.msoMeet.aspx",
    f"{MSO_BASE}/Ajax.ProjectsJson.msoMeet.aspx",
]
DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
MSO_MOBILE_EMULATION = os.getenv("MSO_MOBILE_EMULATION", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _context_kwargs() -> Dict:
    # Keep original desktop mode (lightweight ingest).
    return {"user_agent": DEFAULT_UA}


def _harden_playwright_context(context) -> None:
    """Reduce obvious automation fingerprints."""
    try:
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        context.add_init_script("window.chrome = window.chrome || { runtime: {} };")
    except Exception:
        pass

# Event mapping: EventScore1-4 -> event codes
EVENT_MAP = {
    1: "VT",  # Vault
    2: "UB",  # Bars
    3: "BB",  # Beam
    4: "FX",  # Floor
}


def _is_valid_session_code(code: Optional[str]) -> bool:
    """
    Accept MSO session formats seen in the wild:
    - 01A, 09B (most common in current feeds)
    - A01, B03 (legacy pattern)
    """
    if not code:
        return False
    s = str(code).strip().upper()
    return bool(re.match(r"^(\d{2}[A-Z]|[A-Z]\d{2})$", s))


def _overlay_dismiss_js() -> str:
    return """
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


def _fetch_scores_from_page_network(meet_id: str) -> List[Dict]:
    """
    Fallback: capture MSO's own lookup_scores JSON responses from browser network.
    This bypasses desktop rendering/template bugs where table rows are not drawn.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    captured_payloads: List[dict] = []
    seen_urls = set()
    meet_url = f"{MSO_BASE}/R{meet_id}"

    def _maybe_capture(resp):
        try:
            # MSO puts the useful discriminator (QueryID=lookup_scores) inside the JSON,
            # so don't rely on it being present in the URL.
            if "msoMeet.aspx" not in resp.url:
                return
            if "Ajax" not in resp.url:
                return
            if resp.status != 200:
                return
            if resp.url in seen_urls:
                return
            payload = None
            try:
                payload = resp.json()
            except Exception:
                # Some responses may be served with a misleading content-type
                txt = resp.text()
                try:
                    payload = json.loads(txt)
                except Exception:
                    payload = None

            if isinstance(payload, dict) and payload.get("results"):
                seen_urls.add(resp.url)
                captured_payloads.append(payload)
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**_context_kwargs())
        page = context.new_page()
        page.on("response", _maybe_capture)

        page.goto(meet_url, timeout=30000, wait_until="networkidle")
        page.wait_for_timeout(1500)
        try:
            page.evaluate(_overlay_dismiss_js())
        except Exception:
            pass
        page.wait_for_timeout(1000)

        # In practice, lookup_scores usually fires on initial render as well.
        # We still attempt a couple session changes to trigger additional calls.
        try:
            for _ in range(1):
                page.evaluate(_overlay_dismiss_js())
                page.wait_for_timeout(300)
                try:
                    page.click("a.session.btn", timeout=2000, force=True)
                except Exception:
                    page.evaluate("() => { const el = document.querySelector('a.session.btn'); if (el) el.click(); }")
                page.wait_for_timeout(700)
                items = page.query_selector_all(".session-picker-item")
                for idx, item in enumerate(items[:12]):
                    txt = (item.inner_text() or "").strip().lower()
                    if "combined" in txt:
                        continue
                    try:
                        item.click(timeout=2000, force=True)
                    except Exception:
                        page.evaluate("(el) => el.click()", item)
                    page.wait_for_timeout(1000)
        except Exception:
            pass

        browser.close()

    rows: List[Dict] = []
    for payload in captured_payloads:
        rows.extend(_parse_api_response(payload, meet_id))
    if rows:
        logger.info(
            "Captured %d lookup_scores payloads via network fallback → %d rows",
            len(captured_payloads),
            len(rows),
        )
    return rows


def _common_session_guesses(limit_per_letter: int = 10) -> List[str]:
    """
    Session codes MSO has used in current dropdowns:
    - 01A, 03B, etc.
    Keep this bounded to avoid long runtimes when session discovery fails.
    """
    guesses: List[str] = []
    for suffix in ("A", "B", "C", "D"):
        for i in range(1, limit_per_letter + 1):
            guesses.append(f"{i:02d}{suffix}")
    # Also include a few legacy variants for safety.
    guesses.extend(["A01", "B01", "C01", "A02", "B02", "C02"])
    return guesses


def _try_parse_json_blob(text: str) -> Optional[dict]:
    """Try to parse a JSON object from a response that might have wrong content-type."""
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Try to extract the first {...} blob if response wraps JSON in HTML/script.
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            blob = text[start : end + 1]
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return None


def scrape_mso_meet_api(mso_url: str) -> List[Dict]:
    """
    Main entry: scrape all result rows from a MSO meet using the JSON API.

    Args:
        mso_url: Full URL to the meet page (e.g., /Results/36233)

    Returns:
        List of raw score dicts with placement data
    """
    logger.info("Scraping MSO meet via API: %s", mso_url)

    meet_id = _extract_meet_id_from_url(mso_url)
    if not meet_id:
        logger.error("Could not extract meet ID from URL: %s", mso_url)
        return []

    # Get all sessions for this meet
    sessions = _get_sessions_for_meet(meet_id)
    if not sessions:
        logger.warning("No sessions found for meet %s, trying default", meet_id)
        sessions = [None]  # Try without session filter

    all_rows = []
    for session in sessions:
        rows = _fetch_scores_from_api(meet_id, session)
        all_rows.extend(rows)
        logger.info("  Session %s → %d rows", session or "ALL", len(rows))

    if not all_rows:
        logger.info("API calls returned 0 rows; trying session-guesses + network fallback")
        session_guesses = _common_session_guesses(limit_per_letter=10)
        for guess in session_guesses:
            rows = _fetch_scores_from_api(meet_id, guess)
            if rows:
                all_rows.extend(rows)
                logger.info("  Session guess %s → %d rows", guess, len(rows))
                break

    if not all_rows:
        logger.info("Session guesses returned 0 rows; trying network-capture fallback")
        all_rows = _fetch_scores_from_page_network(meet_id)

    logger.info("MSO API scraped %d total rows from %s", len(all_rows), mso_url)
    return all_rows


def _extract_meet_id_from_url(url: str) -> Optional[str]:
    """Extract numeric meet ID from /Results/36233 or similar URLs."""
    match = re.search(r"/Results/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/R(\d+)", url, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _get_sessions_for_meet(meet_id: str) -> List[Optional[str]]:
    """
    Discover all sessions for a meet by scraping the HTML page dropdown.
    Returns list of session codes, or [None] if we can't determine sessions.
    """
    # Skip HTML-only scraping since dropdown is JavaScript-rendered
    # Go straight to Playwright which can handle JavaScript
    
    # Try using Playwright to get sessions from JavaScript-rendered dropdown
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
        
        logger.info("Trying Playwright to discover sessions from dropdown")
        meet_url = f"{MSO_BASE}/Results/{meet_id}"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(**_context_kwargs())
            page = context.new_page()
            page.goto(meet_url, timeout=30000, wait_until="networkidle")
            
            # Wait a bit for JavaScript to render
            page.wait_for_timeout(2000)
            
            # Dismiss any overlay using JavaScript injection (same approach as HTML scraper)
            DISMISS_OVERLAY_JS = _overlay_dismiss_js()
            try:
                page.evaluate(DISMISS_OVERLAY_JS)
                page.wait_for_timeout(500)
            except Exception:
                pass
            
            # Try to click the session dropdown to open it
            sessions = set()
            try:
                # Wait for page to be ready after overlay dismissal
                page.wait_for_timeout(1000)
                
                # Try to click session button to open dropdown, but handle overlay blocking
                try:
                    session_btn = page.wait_for_selector('a.session.btn', timeout=5000)
                    # Try clicking, but if overlay blocks it, dismiss overlay and retry
                    try:
                        session_btn.click(timeout=3000)
                    except Exception:
                        # Overlay might have appeared, dismiss it again and retry
                        page.evaluate(DISMISS_OVERLAY_JS)
                        page.wait_for_timeout(500)
                        session_btn = page.wait_for_selector('a.session.btn', timeout=3000)
                        try:
                            session_btn.click(timeout=3000, force=True)
                        except Exception:
                            page.evaluate("() => { const el = document.querySelector('a.session.btn'); if (el) el.click(); }")
                    page.wait_for_timeout(1000)  # Wait for dropdown to open
                except Exception as e:
                    logger.warning("Could not click session dropdown: %s", e)
                    raise  # Re-raise to trigger fallback
                
                # Get all session picker items
                session_elements = page.query_selector_all('.session-picker-item')
                logger.info("Found %d session picker items", len(session_elements))
                
                # Extract session codes from each item
                for i, elem in enumerate(session_elements):
                    try:
                        # Get text to see what this item is
                        text = elem.inner_text().strip()
                        logger.debug("Session item %d: text='%s'", i, text)
                        
                        # Skip "Combined" option
                        if 'combined' in text.lower():
                            continue
                        
                        # Try to get session code from various sources
                        session_code = None
                        
                        # Method 1: data-session attribute
                        session_code = elem.get_attribute('data-session')
                        if session_code:
                            logger.debug("  Found via data-session: %s", session_code)
                        
                        # Method 2: data-value attribute
                        if not session_code:
                            session_code = elem.get_attribute('data-value')
                            if session_code:
                                logger.debug("  Found via data-value: %s", session_code)
                        
                        # Method 3: Extract from onclick handler or href
                        if not session_code:
                            onclick = elem.get_attribute('onclick') or ''
                            href = elem.get_attribute('href') or ''
                            # Look for session code in onclick/href
                            for attr_text in [onclick, href]:
                                match = re.search(r'["\']((?:\d{2}[A-Z])|(?:[A-Z]\d{2}))["\']', attr_text)
                                if match:
                                    session_code = match.group(1)
                                    logger.debug("  Found via onclick/href: %s", session_code)
                                    break
                        
                        # Method 4: Extract from text content (e.g., "Session A01")
                        if not session_code:
                            match = re.search(r'\b((?:\d{2}[A-Z])|(?:[A-Z]\d{2}))\b', text)
                            if match:
                                session_code = match.group(1)
                                logger.debug("  Found via text: %s", session_code)
                        
                        # Validate and add session code
                        if _is_valid_session_code(session_code):
                            sessions.add(str(session_code).strip().upper())
                            logger.info("  Valid session code found: %s", session_code)
                        else:
                            logger.debug("  Could not extract valid session code from: %s", text)
                    except Exception as e:
                        logger.debug("  Error processing session item %d: %s", i, e)
                        continue
                
                # Also check page source for session codes in JavaScript
                page_content = page.content()
                soup = BeautifulSoup(page_content, "html.parser")
                
                # Look in script tags for session arrays/objects
                for script in soup.find_all("script"):
                    if script.string:
                        # Look for patterns like: sessions: ["A01", "B02"] or sessionList = ["A01"]
                        # More comprehensive pattern
                        matches = re.findall(r'["\']((?:\d{2}[A-Z])|(?:[A-Z]\d{2}))["\']', script.string)
                        for match in matches:
                            if _is_valid_session_code(match):
                                sessions.add(str(match).strip().upper())
                                logger.debug("Found session code from script: %s", match)
                
            except Exception as e:
                logger.warning("Could not extract sessions via Playwright dropdown: %s", e)
                import traceback
                logger.debug(traceback.format_exc())
            
            browser.close()
            
            # Filter out template placeholders and invalid session codes
            valid_sessions = {
                str(s).strip().upper()
                for s in sessions
                if s and not str(s).startswith("#") and _is_valid_session_code(str(s))
            }
            
            if valid_sessions:
                session_list = sorted(list(valid_sessions))
                logger.info("Found %d sessions via Playwright: %s", len(session_list), session_list)
                return session_list
    except ImportError:
        logger.debug("Playwright not available, skipping Playwright fallback")
    except Exception as exc:
        logger.debug("Playwright session discovery failed: %s", exc)
    
    # Fallback: Try to discover sessions by testing common session codes
    # This is slower but works if HTML scraping fails
    logger.info("Trying to discover sessions by testing common codes")
    # Include both legacy (A01/B02) and current (01A/09B) conventions.
    common_sessions = [
        "A01", "A02", "A03", "A04", "A05",
        "B01", "B02", "B03", "B04", "B05",
        "C01", "C02", "C03", "C04", "C05",
    ] + [f"{i:02d}{suffix}" for i in range(1, 21) for suffix in ("A", "B", "C", "D")]
    
    # Use a session to maintain cookies
    test_session = requests.Session()
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": f"{MSO_BASE}/Results/{meet_id}",
        "X-Requested-With": "XMLHttpRequest",
    }
    
    # First visit the page to get cookies
    try:
        meet_url = f"{MSO_BASE}/Results/{meet_id}"
        test_session.get(meet_url, headers=headers, timeout=10)
    except Exception:
        pass
    
    found_sessions = []
    endpoint_urls = MSO_API_ENDPOINTS[:]
    for session_code in common_sessions:
        test_params = {
            "LookupIndex": "1",
            "p_meetid": meet_id,
            "p_scoresid": "",
            "p_eventid": "",
            "p_session": session_code,
            "p_division": "",
            "limit": "10",  # Small limit just to check if session exists
        }
        
        try:
            for api_endpoint in endpoint_urls:
                resp = test_session.get(
                    api_endpoint, params=test_params, headers=headers, timeout=10
                )
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    data = _try_parse_json_blob(resp.text)
                # Check if we got any rows back
                if isinstance(data, dict) and "results" in data:
                    for result in data.get("results", []):
                        if isinstance(result, dict) and "result" in result:
                            rows = result.get("result", {}).get("row", [])
                            if rows:
                                found_sessions.append(session_code)
                                logger.debug("Session %s has data", session_code)
                                break
                if found_sessions and found_sessions[-1] == session_code:
                    break
        except Exception:
            continue
    
    if found_sessions:
        logger.info("Found %d sessions by testing codes: %s", len(found_sessions), found_sessions)
        return found_sessions
    
    # Last fallback: return None to fetch all sessions at once
    logger.warning("Could not discover sessions for meet %s, will try fetching all at once", meet_id)
    return [None]


def _fetch_scores_from_api(meet_id: str, session: Optional[str] = None) -> List[Dict]:
    """
    Fetch scores from MSO API for a specific meet and session.

    Args:
        meet_id: Numeric meet ID (e.g., "36233")
        session: Session code (e.g., "B03") or None for all sessions

    Returns:
        List of score dicts
    """
    # Try both endpoint spellings because they vary slightly.
    endpoint_urls = MSO_API_ENDPOINTS[:]

    params = {
        "LookupIndex": "1",
        "p_meetid": meet_id,
        "p_scoresid": "",
        "p_eventid": "",
        "p_session": session or "",
        "p_division": "",
        "limit": "5000",
    }

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{MSO_BASE}/Results/{meet_id}",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Try using Playwright to make API call with proper browser context/cookies
    # This is more reliable since MSO API seems to require browser session
    try:
        from playwright.sync_api import sync_playwright
        
        logger.debug("Using Playwright to fetch API for meet %s, session %s", meet_id, session or "ALL")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(**_context_kwargs())
            page = context.new_page()
            
            # First visit the meet page to establish session
            meet_url = f"{MSO_BASE}/Results/{meet_id}"
            page.goto(meet_url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(1000)
            
            for api_endpoint in endpoint_urls:
                # Now make the API call through the browser context
                api_url_with_params = (
                    f"{api_endpoint}?" + "&".join([f"{k}={v}" for k, v in params.items()])
                )

                # Use context.request so cookies/session from the browser context are included.
                api_resp = context.request.get(api_url_with_params, headers=headers)

                if api_resp.status != 200:
                    logger.debug(
                        "Playwright API call failed with status %s (endpoint=%s, session=%s)",
                        api_resp.status,
                        api_endpoint,
                        session,
                    )
                    continue

                try:
                    data = api_resp.json()
                    rows = _parse_api_response(data, meet_id)
                    if rows:
                        browser.close()
                        return rows
                except Exception:
                    pass

                raw_text = api_resp.text()
                parsed = _try_parse_json_blob(raw_text)
                if parsed:
                    rows = _parse_api_response(parsed, meet_id)
                    if rows:
                        browser.close()
                        return rows

            browser.close()
    except ImportError:
        logger.debug("Playwright not available, trying requests")
    except Exception as e:
        logger.debug("Playwright API call failed: %s", e)
    
    # Fallback to requests (may fail if API requires browser context)
    session_obj = requests.Session()
    
    # First, visit the meet page to get cookies (required by MSO API)
    try:
        meet_url = f"{MSO_BASE}/Results/{meet_id}"
        session_obj.get(meet_url, headers=headers, timeout=30)
    except Exception as e:
        logger.debug("Could not fetch meet page for cookies: %s", e)

    try:
        for api_endpoint in endpoint_urls:
            resp = session_obj.get(
                api_endpoint, params=params, headers=headers, timeout=30
            )
            resp.raise_for_status()

            # Try to parse JSON regardless of content-type header.
            data = None
            try:
                data = resp.json()
            except ValueError:
                data = _try_parse_json_blob(resp.text)

            if not data:
                content_type = resp.headers.get("Content-Type", "")
                logger.warning(
                    "MSO API returned unparseable payload type: %s for meet %s (session=%s) (endpoint=%s)",
                    content_type,
                    meet_id,
                    session,
                    api_endpoint,
                )
                logger.debug("Response text (first 500 chars): %s", resp.text[:500])
                logger.info("Trying POST method for meet %s", meet_id)
                try:
                    resp_post = session_obj.post(
                        api_endpoint, data=params, headers=headers, timeout=30
                    )
                    resp_post.raise_for_status()
                    data = _try_parse_json_blob(resp_post.text)
                except Exception:
                    data = None

            if data:
                rows = _parse_api_response(data, meet_id)
                if rows:
                    return rows

        return []

    except requests.RequestException as exc:
        logger.error("MSO API request failed for meet %s: %s", meet_id, exc)
        if hasattr(exc, 'response') and exc.response is not None:
            logger.debug("Response status: %s, Response text: %s", exc.response.status_code, exc.response.text[:500])
        return []
    except Exception as exc:
        logger.error("Unexpected error fetching MSO API for meet %s: %s", meet_id, exc)
        return []


def _parse_api_response(data: dict, meet_id: str) -> List[Dict]:
    """
    Parse MSO API JSON response into score dicts.

    Response structure:
    {
        "results": [{
            "result": {
                "row": [{
                    "AAPlace": "1",
                    "AAScore": "38.625000",
                    "EventPlace1": "2",  # Vault
                    "EventPlace2": "1",  # Bars
                    "EventPlace3": "1",  # Beam
                    "EventPlace4": "1",  # Floor
                    "EventScore1": "9.550000",
                    "EventScore2": "9.750000",
                    "EventScore3": "9.600000",
                    "EventScore4": "9.725000",
                    "div": "Sr 1",
                    "first_name": "Harper",
                    "last_name": "Williams",
                    "gym": "Integrity Athletics",
                    "level": "6",
                    "sess": "B03",
                    ...
                }]
            }
        }]
    }
    """
    rows = []
    
    if not isinstance(data, dict):
        return rows
    
    # Navigate to results[0].result.row[]
    results = data.get("results", [])
    if not results:
        return rows
    
    result_data = results[0].get("result", {})
    row_data = result_data.get("row", [])
    
    if not isinstance(row_data, list):
        return rows
    
    for row in row_data:
        parsed = _parse_api_row(row, meet_id)
        if parsed:
            rows.append(parsed)
    
    return rows


def _parse_api_row(row: dict, meet_id: str) -> Optional[Dict]:
    """
    Parse a single row from the API response into our score format.
    
    Creates separate score records for:
    - AA (All-Around) with AAPlace
    - VT (Vault) with EventPlace1
    - UB (Bars) with EventPlace2
    - BB (Beam) with EventPlace3
    - FX (Floor) with EventPlace4
    """
    # Decode HTML entities in names
    first_name = html.unescape(row.get("first_name", "")).strip()
    last_name = html.unescape(row.get("last_name", "")).strip()
    athlete_name = f"{first_name} {last_name}".strip()
    
    gym = html.unescape(row.get("gym", "")).strip()
    level = str(row.get("level", "")).strip()
    division = html.unescape(row.get("div", "")).strip() or None
    session = str(row.get("sess", "")).strip() or None
    
    if not athlete_name or not gym:
        return None
    
    # Parse scores and places
    aa_score = _parse_float(row.get("AAScore"))
    aa_place = _parse_int(row.get("AAPlace"))
    
    # Individual events
    vault_score = _parse_float(row.get("EventScore1"))
    vault_place = _parse_int(row.get("EventPlace1"))
    
    bars_score = _parse_float(row.get("EventScore2"))
    bars_place = _parse_int(row.get("EventPlace2"))
    
    beam_score = _parse_float(row.get("EventScore3"))
    beam_place = _parse_int(row.get("EventPlace3"))
    
    floor_score = _parse_float(row.get("EventScore4"))
    floor_place = _parse_int(row.get("EventPlace4"))
    
    # Return a dict with all event scores (will be split into separate records by normalizer)
    return {
        "athlete_name": athlete_name,
        "gym": gym,
        "level": level or None,
        "division": division,
        "session": session,
        "meet_id": f"MSO-{meet_id}",
        "source": "mso_api",
        # All-Around
        "aa_score": aa_score,
        "aa_place": aa_place,
        # Individual events with placements
        "vault": vault_score,
        "vault_place": vault_place,
        "bars": bars_score,
        "bars_place": bars_place,
        "beam": beam_score,
        "beam_place": beam_place,
        "floor": floor_score,
        "floor_place": floor_place,
        "raw_row": row,  # Keep original for debugging
    }


def _parse_float(value) -> Optional[float]:
    """Safely parse float value."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> Optional[int]:
    """
    Safely parse int value, handling tied places like '3T'.
    
    Handles ties by extracting the numeric part:
    - "3T" -> 3 (tied for 3rd place)
    - "1T" -> 1 (tied for 1st place)
    - "5" -> 5 (no tie)
    
    The "T" suffix indicates a tie, but we store just the numeric placement
    since multiple athletes can share the same place value.
    """
    if value is None or value == "":
        return None
    # Handle tied places (e.g., "3T" -> 3) by extracting leading digits
    m = re.match(r"(\d+)", str(value).strip())
    if m:
        return int(m.group(1))
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
