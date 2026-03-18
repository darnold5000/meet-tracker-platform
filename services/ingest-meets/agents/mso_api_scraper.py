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
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

MSO_BASE = "https://www.meetscoresonline.com"
MSO_API_ENDPOINT = f"{MSO_BASE}/Ajax.Projects.Json.msoMeet.aspx"

# Event mapping: EventScore1-4 -> event codes
EVENT_MAP = {
    1: "VT",  # Vault
    2: "UB",  # Bars
    3: "BB",  # Beam
    4: "FX",  # Floor
}


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
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            page.goto(meet_url, timeout=30000, wait_until="networkidle")
            
            # Wait a bit for JavaScript to render
            page.wait_for_timeout(2000)
            
            # Dismiss any overlay using JavaScript injection (same approach as HTML scraper)
            DISMISS_OVERLAY_JS = """
                ['showmessage_overlay', 'showmessage', 'IGCOfferModal'].forEach(id => {
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                });
                document.querySelectorAll(
                    '.modal-backdrop, .modal.show, [id*="overlay"], [id*="modal"]'
                ).forEach(e => e.style.display = 'none');
                document.body.style.overflow = 'auto';
            """
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
                        session_btn.click(timeout=3000)
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
                                match = re.search(r'["\']([A-Z]\d{2})["\']', attr_text)
                                if match:
                                    session_code = match.group(1)
                                    logger.debug("  Found via onclick/href: %s", session_code)
                                    break
                        
                        # Method 4: Extract from text content (e.g., "Session A01")
                        if not session_code:
                            match = re.search(r'\b([A-Z]\d{2})\b', text)
                            if match:
                                session_code = match.group(1)
                                logger.debug("  Found via text: %s", session_code)
                        
                        # Validate and add session code
                        if session_code and re.match(r'^[A-Z]\d{2}$', session_code):
                            sessions.add(session_code)
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
                        matches = re.findall(r'["\']([A-Z]\d{2})["\']', script.string)
                        for match in matches:
                            if re.match(r'^[A-Z]\d{2}$', match):
                                sessions.add(match)
                                logger.debug("Found session code from script: %s", match)
                
            except Exception as e:
                logger.warning("Could not extract sessions via Playwright dropdown: %s", e)
                import traceback
                logger.debug(traceback.format_exc())
            
            browser.close()
            
            # Filter out template placeholders and invalid session codes
            valid_sessions = {s for s in sessions if s and not s.startswith('#') and re.match(r'^[A-Z]\d{2}$', s)}
            
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
    common_sessions = ["A01", "A02", "A03", "A04", "A05", 
                       "B01", "B02", "B03", "B04", "B05",
                       "C01", "C02", "C03", "C04", "C05"]
    
    # Use a session to maintain cookies
    test_session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
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
            resp = test_session.get(MSO_API_ENDPOINT, params=test_params, headers=headers, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # Check if we got any rows back
                    if isinstance(data, dict) and "results" in data:
                        for result in data.get("results", []):
                            if isinstance(result, dict) and "result" in result:
                                rows = result.get("result", {}).get("row", [])
                                if rows:
                                    found_sessions.append(session_code)
                                    logger.debug("Session %s has data", session_code)
                                    break
                except ValueError:
                    # Not JSON, skip
                    continue
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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            
            # First visit the meet page to establish session
            meet_url = f"{MSO_BASE}/Results/{meet_id}"
            page.goto(meet_url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(1000)
            
            # Now make the API call through the browser context
            api_url_with_params = f"{MSO_API_ENDPOINT}?" + "&".join([f"{k}={v}" for k, v in params.items()])
            
            # Use page.request to make API call with browser cookies
            api_resp = page.request.get(api_url_with_params, headers=headers)
            
            if api_resp.status == 200:
                try:
                    data = api_resp.json()
                    browser.close()
                    rows = _parse_api_response(data, meet_id)
                    return rows
                except Exception as e:
                    logger.debug("Playwright API call returned non-JSON: %s", e)
                    browser.close()
            else:
                logger.debug("Playwright API call failed with status %s", api_resp.status)
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
        resp = session_obj.get(MSO_API_ENDPOINT, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # Try to parse JSON regardless of content-type header
        # Sometimes MSO returns JSON but with wrong content-type
        data = None
        try:
            data = resp.json()
        except ValueError:
            # If JSON parsing fails, check content-type
            content_type = resp.headers.get('Content-Type', '')
            if 'application/json' not in content_type and 'text/javascript' not in content_type:
                logger.warning("MSO API returned non-JSON content type: %s for meet %s", content_type, meet_id)
                logger.debug("Response text (first 500 chars): %s", resp.text[:500])
                # Try POST method as fallback
                logger.info("Trying POST method for meet %s", meet_id)
                try:
                    resp_post = session_obj.post(MSO_API_ENDPOINT, data=params, headers=headers, timeout=30)
                    resp_post.raise_for_status()
                    try:
                        data = resp_post.json()
                        logger.info("POST method succeeded for meet %s", meet_id)
                    except ValueError:
                        logger.warning("POST method also returned non-JSON for meet %s", meet_id)
                        return []
                except Exception as e:
                    logger.debug("POST method failed: %s", e)
                    return []
            else:
                # Content-type says JSON but parsing failed
                logger.error("MSO API returned invalid JSON for meet %s", meet_id)
                logger.debug("Response text (first 500 chars): %s", resp.text[:500])
                return []
        
        if data is None:
            return []
        
        rows = _parse_api_response(data, meet_id)
        return rows

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
