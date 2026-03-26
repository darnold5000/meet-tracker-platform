"""
APScheduler job definitions.

Job schedule:
  - meet_discovery     → daily at 6am
  - scorecat_polling   → every 10s (only for active meets)
  - mso_scrape         → every 60 minutes
  - website_crawl      → every 6 hours
  - varsity_cheer_mvp_sync → every N hours (optional; VARSITY_INGEST_ENABLED=1)
"""

import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MEET_DISCOVERY_HOUR = int(os.getenv("MEET_DISCOVERY_HOUR", "6"))
MSO_SCRAPE_INTERVAL_MINUTES = int(os.getenv("MSO_SCRAPE_INTERVAL_MINUTES", "60"))
WEBSITE_CRAWL_INTERVAL_HOURS = int(os.getenv("WEBSITE_CRAWL_INTERVAL_HOURS", "6"))
VARSITY_INGEST_INTERVAL_HOURS = int(os.getenv("VARSITY_INGEST_INTERVAL_HOURS", "6"))
VARSITY_RESULTS_MAX_ITEMS = int(os.getenv("VARSITY_RESULTS_MAX_ITEMS", "200"))


# ── Job functions ─────────────────────────────────────────────────────────────

def job_meet_discovery():
    """Daily: discover new meets from MSO and USAG calendar."""
    logger.info("[SCHEDULER] Running meet discovery")
    from agents.meet_discovery import discover_meets
    from agents.source_detector import detect_sources

    meets = discover_meets()
    logger.info("[SCHEDULER] Discovered %d meets", len(meets))

    for meet in meets:
        sources = detect_sources(meet)
        logger.info("  Meet %s | sources=%s", meet.get("meet_id"), [s.value for s in sources])


def job_mso_scrape():
    """Hourly: scrape MSO result pages for all known meets."""
    logger.info("[SCHEDULER] Running MSO scrape job")
    from db.database import SessionLocal
    from db.models import Meet
    from agents.mso_scraper import scrape_mso_meet
    from core.normalizer import normalize_mso_record
    from core.hasher import is_duplicate, mark_seen

    db = SessionLocal()
    try:
        meets = db.query(Meet).filter(Meet.mso_url.isnot(None)).all()
        for meet in meets:
            try:
                raw_rows = scrape_mso_meet(meet.mso_url)
                new_count = 0
                for raw in raw_rows:
                    normalized = normalize_mso_record(raw)
                    if not is_duplicate(normalized):
                        mark_seen(normalized)
                        new_count += 1
                if new_count:
                    logger.info("[MSO] Meet %s: %d new records", meet.meet_id, new_count)
            except Exception as exc:
                logger.error("[MSO] Failed for meet %s: %s", meet.meet_id, exc)
    finally:
        db.close()


def job_varsity_cheer_mvp_sync():
    """Periodic: Varsity TV schedule + results index → CheerMvpMeet upserts."""
    logger.info("[SCHEDULER] Running Varsity → cheer_mvp_meets sync")
    from agents.varsity_client import sync_cheer_mvp_meets_from_varsity
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        stats = sync_cheer_mvp_meets_from_varsity(
            db, results_max_items=VARSITY_RESULTS_MAX_ITEMS
        )
    finally:
        db.close()

    logger.info(
        "[SCHEDULER] Varsity sync done: inserted=%s updated=%s merged=%s",
        stats["inserted"],
        stats["updated"],
        stats["total_merged"],
    )


def job_website_crawl():
    """Every 6 hours: parse meet websites for PDF/HTML results."""
    logger.info("[SCHEDULER] Running website crawl job")
    from db.database import SessionLocal
    from db.models import Meet
    from agents.website_parser import parse_website
    from core.normalizer import normalize_website_record
    from core.hasher import is_duplicate, mark_seen

    db = SessionLocal()
    try:
        meets = db.query(Meet).filter(Meet.website_url.isnot(None)).all()
        for meet in meets:
            try:
                raw_rows = parse_website(meet.website_url, meet.meet_id)
                new_count = 0
                for raw in raw_rows:
                    normalized = normalize_website_record(raw)
                    if not is_duplicate(normalized):
                        mark_seen(normalized)
                        new_count += 1
                if new_count:
                    logger.info("[WEBSITE] Meet %s: %d new records", meet.meet_id, new_count)
            except Exception as exc:
                logger.error("[WEBSITE] Failed for meet %s: %s", meet.meet_id, exc)
    finally:
        db.close()


# ── Scheduler setup ───────────────────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/New_York")
    varsity_enabled = os.getenv("VARSITY_INGEST_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    # Daily meet discovery
    scheduler.add_job(
        job_meet_discovery,
        trigger=CronTrigger(hour=MEET_DISCOVERY_HOUR, minute=0),
        id="meet_discovery",
        name="Daily meet discovery",
        replace_existing=True,
    )

    # Hourly MSO scrape
    scheduler.add_job(
        job_mso_scrape,
        trigger=IntervalTrigger(minutes=MSO_SCRAPE_INTERVAL_MINUTES),
        id="mso_scrape",
        name="MSO results scrape",
        replace_existing=True,
    )

    # 6-hour website crawl
    scheduler.add_job(
        job_website_crawl,
        trigger=IntervalTrigger(hours=WEBSITE_CRAWL_INTERVAL_HOURS),
        id="website_crawl",
        name="Meet website crawl",
        replace_existing=True,
    )

    if varsity_enabled:
        scheduler.add_job(
            job_varsity_cheer_mvp_sync,
            trigger=IntervalTrigger(hours=VARSITY_INGEST_INTERVAL_HOURS),
            id="varsity_cheer_mvp_sync",
            name="Varsity TV → cheer_mvp_meets",
            replace_existing=True,
        )

    return scheduler


def start_scheduler():
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [j.id for j in scheduler.get_jobs()])
    return scheduler
