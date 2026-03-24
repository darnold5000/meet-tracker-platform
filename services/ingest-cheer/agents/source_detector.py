"""
Source Detection

Given a meet URL or page content, determine which ingestion agent to use.
A single meet may have multiple sources.
"""

from enum import Enum
from typing import List
import logging

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    SCORECAT = "scorecat"
    MSO = "mso"
    WEBSITE_PDF = "website_pdf"
    WEBSITE_HTML = "website_html"
    UNKNOWN = "unknown"


def detect_sources(meet: dict) -> List[SourceType]:
    """
    Inspect a meet dict and return all applicable source types.

    Priority:
    1. Explicit ScoreCat URL
    2. Explicit MSO URL
    3. Website URL — infer PDF or HTML
    """
    sources: List[SourceType] = []

    scorecat_url = meet.get("scorecat_url", "") or ""
    mso_url = meet.get("mso_url", "") or ""
    website_url = meet.get("website_url", "") or ""

    if "scorecat.com" in scorecat_url.lower():
        sources.append(SourceType.SCORECAT)
        logger.debug("Meet %s: detected ScoreCat source", meet.get("meet_id"))

    if "meetscoresonline.com" in mso_url.lower():
        sources.append(SourceType.MSO)
        logger.debug("Meet %s: detected MSO source", meet.get("meet_id"))

    if website_url:
        if website_url.lower().endswith(".pdf"):
            sources.append(SourceType.WEBSITE_PDF)
            logger.debug("Meet %s: detected website PDF source", meet.get("meet_id"))
        else:
            sources.append(SourceType.WEBSITE_HTML)
            logger.debug("Meet %s: detected website HTML source", meet.get("meet_id"))

    if not sources:
        sources.append(SourceType.UNKNOWN)
        logger.warning("Meet %s: no source detected", meet.get("meet_id"))

    return sources


def extract_scorecat_meet_id(scorecat_url: str) -> str | None:
    """
    Extract the ScoreCat meetId parameter from a URL.
    Examples:
      https://www.scorecat.com/Competition/Results/12345
      https://www.scorecat.com/?meetId=12345
    """
    import re
    patterns = [
        r"[?&]meetId=(\d+)",
        r"/Results/(\d+)",
        r"/Competition/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, scorecat_url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
