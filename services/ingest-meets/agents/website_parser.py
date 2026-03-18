"""
Meet Website Parser

Handles individual meet websites that publish scores as:
- PDF score sheets
- HTML result tables
- CSV exports

Routes to the correct parser based on content type.
"""

import io
import re
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; USAGTracker/1.0)"}


def parse_website(url: str, meet_id: str) -> List[Dict]:
    """
    Download a meet result file/page and route to the correct parser.

    Returns:
        List of raw score dicts
    """
    logger.info("Parsing meet website: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
    except requests.RequestException as exc:
        logger.error("Could not fetch %s: %s", url, exc)
        return []

    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return _parse_pdf(resp.content, meet_id)

    if "csv" in content_type or url.lower().endswith(".csv"):
        return _parse_csv(resp.text, meet_id)

    # Default: treat as HTML
    return _parse_html(resp.text, meet_id, url)


def _parse_pdf(content: bytes, meet_id: str) -> List[Dict]:
    """
    Extract text from PDF using pdfplumber.
    Falls back to pytesseract OCR if text extraction yields nothing.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return []

    rows: List[Dict] = []

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        with pdfplumber.open(tmp_path) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )

        if full_text.strip():
            rows = _parse_text_scores(full_text, meet_id, source="website_pdf")
        else:
            logger.warning("pdfplumber extracted no text — trying OCR")
            rows = _parse_pdf_ocr(tmp_path, meet_id)

    finally:
        Path(tmp_path).unlink(missing_ok=True)

    logger.info("PDF parser extracted %d score rows", len(rows))
    return rows


def _parse_pdf_ocr(pdf_path: str, meet_id: str) -> List[Dict]:
    """OCR fallback using pytesseract."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.error("pdf2image or pytesseract not installed for OCR fallback")
        return []

    try:
        images = convert_from_path(pdf_path)
        text = "\n".join(pytesseract.image_to_string(img) for img in images)
        return _parse_text_scores(text, meet_id, source="website_pdf_ocr")
    except Exception as exc:
        logger.error("OCR failed: %s", exc)
        return []


def _parse_text_scores(text: str, meet_id: str, source: str) -> List[Dict]:
    """
    Parse score lines from extracted PDF/OCR text.
    Looks for lines matching: Name  Gym  Score pattern.
    """
    rows = []
    score_pattern = re.compile(
        r"(?P<name>[A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\s+"
        r"(?P<gym>[A-Za-z\s]+?)\s+"
        r"(?P<score>\d{1,2}\.\d{2,3})"
    )

    for line in text.splitlines():
        match = score_pattern.search(line)
        if match:
            rows.append({
                "athlete_name": match.group("name").strip(),
                "gym": match.group("gym").strip(),
                "score": float(match.group("score")),
                "event": "AA",
                "meet_id": meet_id,
                "source": source,
            })

    return rows


def _parse_html(html: str, meet_id: str, url: str) -> List[Dict]:
    """Parse HTML result table from meet website."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    rows: List[Dict] = []

    for table in soup.select("table"):
        headers = [th.get_text(strip=True).lower() for th in table.select("th")]
        if not any(k in headers for k in ["score", "total", "athlete", "name"]):
            continue

        for tr in table.select("tr"):
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if len(cells) < 2:
                continue

            row = dict(zip(headers, cells)) if headers else {}
            name = (row.get("athlete") or row.get("name") or (cells[0] if cells else "")).strip()
            gym = (row.get("gym") or row.get("club") or (cells[1] if len(cells) > 1 else "")).strip()
            score_raw = row.get("score") or row.get("total") or (cells[-1] if cells else "")
            score_match = re.search(r"(\d+\.\d+)", str(score_raw))

            if name and gym and score_match:
                rows.append({
                    "athlete_name": name,
                    "gym": gym,
                    "score": float(score_match.group(1)),
                    "event": "AA",
                    "meet_id": meet_id,
                    "source": "website_html",
                })

    logger.info("HTML parser extracted %d rows from %s", len(rows), url)
    return rows


def _parse_csv(text: str, meet_id: str) -> List[Dict]:
    """Parse a CSV score export."""
    import csv

    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        name = (row.get("Athlete") or row.get("Name") or "").strip()
        gym = (row.get("Gym") or row.get("Club") or "").strip()
        score_raw = row.get("Score") or row.get("Total") or ""
        score_match = re.search(r"(\d+\.\d+)", str(score_raw))

        if name and gym and score_match:
            rows.append({
                "athlete_name": name,
                "gym": gym,
                "score": float(score_match.group(1)),
                "event": "AA",
                "meet_id": meet_id,
                "source": "website_csv",
            })

    logger.info("CSV parser extracted %d rows", len(rows))
    return rows
