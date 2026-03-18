import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')

from agents.mso_scraper import scrape_mso_meet
from core.normalizer import normalize_mso_record

# Import save_scores and save_meets from ingest
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ingest", "ingest.py")
ingest = importlib.util.load_from_spec(spec)
spec.loader.exec_module(ingest)

meet = {
    "meet_id": "MSO-SWING-2026",
    "name": "2026 Swing Into Spring Invitational",
    "mso_url": "https://www.meetscoresonline.com/Results/36233",
    "source": "mso", "state": "OH",
    "start_date": "2026-02-27", "location": "Hamilton, OH",
}

print(f"Saving meet record...")
ingest.save_meets([meet])

print(f"Scraping scores from MSO...")
raw_rows = scrape_mso_meet(meet["mso_url"])
normalized = [normalize_mso_record(r) for r in raw_rows]
print(f"Scraped {len(normalized)} athlete rows")

if normalized:
    saved, dupes = ingest.save_scores(normalized, meet["meet_id"])
    print(f"Saved: {saved} new score records | Skipped: {dupes} dupes")

    # Show Flip Zone athletes
    fz = [r for r in normalized if r.get("gym_name") and "flip zone" in r["gym_name"].lower()]
    print(f"\nFlip Zone athletes found: {len(fz)}")
    for r in fz:
        print(f"  {r.get('athlete_name'):<30} L{r.get('level')}  AA={r.get('score')}")
else:
    print("No rows found.")
