"""
Meet Discovery Agent

Finds upcoming gymnastics meets from:
- MeetScoresOnline meet index (homepage + per-state pages)
- MSO search endpoint (/Results?search=State)
- USAG regional event calendar (HTML scrape)
"""

import logging
import re
from datetime import date, datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MSO_BASE_URL = "https://www.meetscoresonline.com"
MSO_INDEX_URL = MSO_BASE_URL
REQUEST_TIMEOUT = 30

# Target states for focused discovery
TARGET_STATES = ["IN", "OH", "MI", "CA"]


def discover_meets(states: List[str] = None) -> List[Dict]:
    """
    Main entry point. Returns a list of normalized meet dicts.
    Scrapes homepage + per-state pages + search endpoint (/Results?search=State) for focused discovery.

    Args:
        states: List of state abbreviations to scrape (defaults to TARGET_STATES)
    """
    if states is None:
        states = TARGET_STATES

    meets: List[Dict] = []
    seen_ids: set = set()
    states_set = set(s.upper() for s in states)  # Normalize to uppercase for comparison

    # Skip homepage scraping when doing state-specific discovery to avoid pulling meets from all states
    # The state-specific pages and search endpoints provide comprehensive coverage
    # Homepage scraping is only useful when discovering meets across all default states
    # (We'll rely on state pages and search endpoints for focused discovery)

    # Scrape per-state all-results pages
    for state in states:
        url = f"{MSO_BASE_URL}/{state}/Results.All"
        try:
            for m in _discover_from_mso_page(url, state=state):
                if m["meet_id"] not in seen_ids:
                    seen_ids.add(m["meet_id"])
                    m["state"] = state
                    meets.append(m)
        except Exception as exc:
            logger.error("MSO state %s discovery failed: %s", state, exc)
    
    # Scrape search endpoint for each state (more comprehensive discovery)
    # Use state name for better results (e.g., "Indiana" instead of "IN")
    state_names = {
        "IN": "Indiana",
        "OH": "Ohio", 
        "MI": "Michigan",
        "CA": "California",
        "KY": "Kentucky",
        "IL": "Illinois",
    }
    for state in states:
        # Try both state code and state name
        search_terms = [state]
        if state.upper() in state_names:
            search_terms.append(state_names[state.upper()])
        
        for search_term in search_terms:
            search_url = f"{MSO_BASE_URL}/Results?search={search_term}"
            try:
                for m in _discover_from_mso_search(search_url, state=state):
                    if m["meet_id"] not in seen_ids:
                        seen_ids.add(m["meet_id"])
                        m["state"] = state
                        meets.append(m)
            except Exception as exc:
                logger.error("MSO search for %s failed: %s", search_term, exc)

    logger.info("Discovered %d meets total across states %s", len(meets), states)
    return meets


def _discover_from_mso_page(url: str, state: str = None) -> List[Dict]:
    """
    Scrape a single MSO page for meet links.
    Handles two URL patterns:
      - /R36426         (homepage short links)
      - /2026-IN-Grand-Park-Classic  (state results pages slug links)
    """
    meets = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; USAGTracker/1.0)"}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not fetch MSO page %s: %s", url, exc)
        return meets

    soup = BeautifulSoup(resp.text, "lxml")
    seen_slugs: set = set()

    # Pattern 1: short /R<digits> links (homepage)
    for link in soup.find_all("a", href=re.compile(r"^/R\d+$|^https?://www\.meetscoresonline\.com/R\d+")):
        href = link.get("href", "")
        numeric_id = _extract_mso_meet_id(href)
        if not numeric_id or numeric_id in seen_slugs:
            continue
        seen_slugs.add(numeric_id)

        full_url = href if href.startswith("http") else f"{MSO_BASE_URL}{href}"
        name = _extract_meet_name(link)

        meets.append({
            "meet_id": f"MSO-{numeric_id}",
            "name": name,
            "mso_url": full_url,
            "source": "mso",
            "state": state,
            "discovered_at": datetime.utcnow().isoformat(),
        })

    # Pattern 2: slug links like /2026-IN-Grand-Park-Classic (state results pages)
    # These look like /YYYY-ST-Some-Meet-Name
    slug_pattern = re.compile(
        r"^/(\d{4}-[A-Z]{2}-.+)$|^https?://www\.meetscoresonline\.com/(\d{4}-[A-Z]{2}-.+)$"
    )
    for link in soup.find_all("a", href=slug_pattern):
        href = link.get("href", "")
        m = slug_pattern.match(href)
        if not m:
            continue
        slug = m.group(1) or m.group(2)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        full_url = href if href.startswith("http") else f"{MSO_BASE_URL}{href}"

        # Extract state from slug (e.g. 2026-IN-Grand... → IN)
        slug_state = _state_from_slug(slug) or state

        # Build a stable meet_id from the slug
        meet_id = f"MSO-{slug}"

        # Meet name is the link text itself on these pages (e.g. "2026 Grand Park Classic")
        name = link.get_text(strip=True)
        if not name or len(name) < 4:
            name = _slug_to_name(slug)

        # Parse dates, location, facility, and host gym from nearby text
        start_date, end_date, location, facility, host_gym = _extract_meet_metadata(link)

        meets.append({
            "meet_id": meet_id,
            "name": name,
            "mso_url": full_url,
            "source": "mso",
            "state": slug_state,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "facility": facility,
            "host_gym": host_gym,
            "discovered_at": datetime.utcnow().isoformat(),
        })

    logger.info("MSO page %s → %d meets", url, len(meets))
    return meets


def _discover_from_mso_search(url: str, state: str = None) -> List[Dict]:
    """
    Scrape MSO search endpoint (/Results?search=Indiana) for meet links.
    This endpoint returns meets matching the search term, typically using /Results/{ID} pattern.
    """
    meets = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; USAGTracker/1.0)"}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not fetch MSO search %s: %s", url, exc)
        return meets

    soup = BeautifulSoup(resp.text, "lxml")
    seen_ids: set = set()

    # Pattern: /Results/{ID} links (e.g., /Results/36233)
    results_pattern = re.compile(r"^/Results/(\d+)$|^https?://www\.meetscoresonline\.com/Results/(\d+)$")
    for link in soup.find_all("a", href=results_pattern):
        href = link.get("href", "")
        match = results_pattern.match(href)
        if not match:
            continue
        
        numeric_id = match.group(1) or match.group(2)
        if not numeric_id or numeric_id in seen_ids:
            continue
        seen_ids.add(numeric_id)

        full_url = href if href.startswith("http") else f"{MSO_BASE_URL}{href}"
        name = _extract_meet_name(link)
        
        # Try to extract date range, location, facility, and host gym from nearby text
        start_date, end_date, location, facility, host_gym = _extract_meet_metadata(link)

        meets.append({
            "meet_id": f"MSO-{numeric_id}",
            "name": name,
            "mso_url": full_url,
            "source": "mso",
            "state": state,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "facility": facility,
            "host_gym": host_gym,
            "discovered_at": datetime.utcnow().isoformat(),
        })

    # Also check for /R{ID} pattern links (short format)
    for link in soup.find_all("a", href=re.compile(r"^/R\d+$|^https?://www\.meetscoresonline\.com/R\d+")):
        href = link.get("href", "")
        numeric_id = _extract_mso_meet_id(href)
        if not numeric_id or numeric_id in seen_ids:
            continue
        seen_ids.add(numeric_id)

        full_url = href if href.startswith("http") else f"{MSO_BASE_URL}{href}"
        name = _extract_meet_name(link)
        start_date, end_date, location, facility, host_gym = _extract_meet_metadata(link)

        meets.append({
            "meet_id": f"MSO-{numeric_id}",
            "name": name,
            "mso_url": full_url,
            "source": "mso",
            "state": state,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "facility": facility,
            "host_gym": host_gym,
            "discovered_at": datetime.utcnow().isoformat(),
        })

    logger.info("MSO search %s → %d meets", url, len(meets))
    return meets


def _extract_meet_name(link) -> str:
    """
    Try to find the meet name near the Results link.
    MSO puts the name in a paragraph or heading above the link in the same block.
    """
    parent = link.parent
    for _ in range(4):
        if parent is None:
            break
        texts = [t.get_text(strip=True) for t in parent.find_all(["p", "h1", "h2", "h3", "h4", "h5", "strong", "b"])
                 if t.get_text(strip=True) and len(t.get_text(strip=True)) > 5]
        skip = {"results", "live", "men's women's live!", "awaiting scores",
                "starting soon", "closed", "meet complete", "completed", "finished"}
        for text in texts:
            if text.lower() not in skip and len(text) > 5:
                return text
        parent = parent.parent

    return "Unknown Meet"


def _extract_mso_meet_id(href: str) -> Optional[str]:
    """Extract numeric ID from /R36426 or full URL pattern."""
    match = re.search(r"/R(\d+)", href, re.IGNORECASE)
    return match.group(1) if match else None


def _state_from_slug(slug: str) -> Optional[str]:
    """Extract 2-letter state code from slug like '2026-IN-Grand-Park-Classic'."""
    m = re.match(r"^\d{4}-([A-Z]{2})-", slug)
    return m.group(1) if m else None


def _slug_to_name(slug: str) -> str:
    """Convert slug '2026-IN-Grand-Park-Classic' → '2026 Grand Park Classic'."""
    parts = slug.split("-")
    # Remove year and state prefix
    if len(parts) > 2 and parts[0].isdigit() and len(parts[1]) == 2:
        name_parts = parts[2:]
    else:
        name_parts = parts
    return " ".join(name_parts)


def _extract_meet_metadata(link) -> tuple:
    """
    Walk siblings/parents near a meet link to find start/end date, location, facility, and host gym.
    Returns (start_date_or_None, end_date_or_None, location_or_None, facility_or_None, host_gym_or_None).
    """
    start_date = None
    end_date = None
    location = None
    facility = None
    host_gym = None

    parent = link.parent
    for _ in range(5):
        if parent is None:
            break
        text = parent.get_text(separator=" ", strip=True)

        # Parse first/second long-date matches as start/end (if present)
        date_matches = re.findall(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}",
            text,
        )
        if date_matches and start_date is None:
            # re.findall above only returns month names due to groups; use finditer for full match text
            full_matches = list(
                re.finditer(
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}",
                    text,
                )
            )
            try:
                start_date = datetime.strptime(full_matches[0].group(), "%b %d, %Y").date().isoformat()
                if len(full_matches) > 1:
                    end_date = datetime.strptime(full_matches[1].group(), "%b %d, %Y").date().isoformat()
                else:
                    end_date = start_date
            except (ValueError, IndexError):
                pass

        # Try location: "City, ST" pattern
        loc_match = re.search(r"([A-Za-z\s]+,\s*[A-Z]{2})\b", text)
        if loc_match and location is None:
            location = loc_match.group(1).strip()

        if facility is None:
            facility_match = re.search(
                r"(?:Facility|Venue|Location)\s*[:\-]\s*([A-Za-z0-9&'().,\-\/\s]{3,120})",
                text,
                re.IGNORECASE,
            )
            if facility_match:
                facility = facility_match.group(1).strip(" .,-")

        # Try host gym patterns often used on listings
        if host_gym is None:
            host_match = re.search(
                r"(?:Hosted by|Host(?:ed)?\s*Gym|Host)\s*[:\-]\s*([A-Za-z0-9&'().,\-\/\s]{3,80})",
                text,
                re.IGNORECASE,
            )
            if host_match:
                host_gym = host_match.group(1).strip(" .,-")

        if start_date and location and facility and host_gym:
            break
        parent = parent.parent

    return start_date, end_date, location, facility, host_gym


def build_meet_dict(
    meet_id: str,
    name: str,
    location: Optional[str] = None,
    facility: Optional[str] = None,
    state: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    host_gym: Optional[str] = None,
    scorecat_url: Optional[str] = None,
    mso_url: Optional[str] = None,
    website_url: Optional[str] = None,
) -> Dict:
    """Helper to build a normalized meet dict."""
    return {
        "meet_id": meet_id,
        "name": name,
        "location": location,
        "facility": facility,
        "state": state,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "host_gym": host_gym,
        "scorecat_url": scorecat_url,
        "mso_url": mso_url,
        "website_url": website_url,
    }
