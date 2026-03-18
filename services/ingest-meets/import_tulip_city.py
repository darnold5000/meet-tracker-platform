"""
Import Tulip City 2026 results from ScoreCat CSV export.
CSV format: index, Athlete, Gym, Level, Event, Score, Place
"""
import os, sys
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

CSV_PATH = "/Users/darnold_1/Downloads/2026-03-13T14-31_export.csv"
MEET_ID  = "MSO-TULIP-2026"
MEET_NAME = "2026 Tulip City Classic"

# Event name mapping from CSV to DB codes
EVENT_MAP = {
    "AA": "AA", "VT": "VT", "UB": "UB", "BB": "BB", "FX": "FX",
    "Vault": "VT", "Bars": "UB", "Beam": "BB", "Floor": "FX",
}

# Level name mapping: "Level 6" -> "6", "Level 10" -> "10"
def parse_level(raw):
    raw = str(raw).strip()
    if raw.lower().startswith("level "):
        return raw.split(" ", 1)[1].strip()
    return raw

# Place mapping: "#1" -> 1, "—" -> None
def parse_place(raw):
    raw = str(raw).strip()
    m = __import__("re").search(r"(\d+)", raw)
    return int(m.group(1)) if m else None

df = pd.read_csv(CSV_PATH)
df.columns = ["idx", "athlete", "gym", "level", "event", "score", "place"]
df["level"] = df["level"].apply(parse_level)
df["event"] = df["event"].map(EVENT_MAP).fillna(df["event"])
df["place"] = df["place"].apply(parse_place)
df["score"] = pd.to_numeric(df["score"], errors="coerce")

print(f"CSV rows loaded: {len(df)}")
print(f"Levels: {sorted(df['level'].unique())}")
print(f"Events: {sorted(df['event'].unique())}")
print(f"Gyms:   {sorted(df['gym'].unique())}")

fz = df[df["gym"].str.lower().str.contains("flip zone")]
print(f"\nFlip Zone rows: {len(fz)}")
print(fz[["athlete","level","event","score","place"]].to_string(index=False))

confirm = input("\nImport all rows into database? (yes/no): ").strip().lower()
if confirm != "yes":
    print("Cancelled.")
    sys.exit(0)

with engine.begin() as conn:
    # Upsert meet
    existing = conn.execute(text("SELECT id FROM meets WHERE meet_id = :mid"), {"mid": MEET_ID}).fetchone()
    if not existing:
        conn.execute(text("""
            INSERT INTO meets (meet_id, name, state, location, start_date)
            VALUES (:mid, :name, 'MI', 'Holland, MI', '2026-02-07')
        """), {"mid": MEET_ID, "name": MEET_NAME})
        print("Meet record created.")
    meet_row = conn.execute(text("SELECT id FROM meets WHERE meet_id = :mid"), {"mid": MEET_ID}).fetchone()
    meet_db_id = meet_row[0]

    inserted = 0
    skipped  = 0

    for _, row in df.iterrows():
        gym_name = str(row["gym"]).strip().title()

        # Upsert gym
        gym_row = conn.execute(text(
            "SELECT id FROM gyms WHERE canonical_name = :n"
        ), {"n": gym_name}).fetchone()
        if not gym_row:
            conn.execute(text(
                "INSERT INTO gyms (name, canonical_name) VALUES (:n, :n)"
            ), {"n": gym_name})
            gym_row = conn.execute(text(
                "SELECT id FROM gyms WHERE canonical_name = :n"
            ), {"n": gym_name}).fetchone()
        gym_id = gym_row[0]

        # Upsert athlete (scoped to gym — no cross-gym collisions)
        athlete_name = str(row["athlete"]).strip().title()
        ath_row = conn.execute(text(
            "SELECT id FROM athletes WHERE canonical_name = :n AND gym_id = :gid"
        ), {"n": athlete_name, "gid": gym_id}).fetchone()
        if not ath_row:
            conn.execute(text(
                "INSERT INTO athletes (canonical_name, gym_id, level) VALUES (:n, :gid, :lvl)"
            ), {"n": athlete_name, "gid": gym_id, "lvl": row["level"]})
            ath_row = conn.execute(text(
                "SELECT id FROM athletes WHERE canonical_name = :n AND gym_id = :gid"
            ), {"n": athlete_name, "gid": gym_id}).fetchone()
        athlete_id = ath_row[0]

        # Upsert alias
        existing_alias = conn.execute(text(
            "SELECT id FROM athlete_aliases WHERE athlete_id = :aid AND raw_name = :n"
        ), {"aid": athlete_id, "n": athlete_name}).fetchone()
        if not existing_alias:
            conn.execute(text(
                "INSERT INTO athlete_aliases (athlete_id, raw_name, source) VALUES (:aid, :n, 'scorecat')"
            ), {"aid": athlete_id, "n": athlete_name})

        # Build score record hash
        import hashlib
        hash_str = f"{meet_db_id}:{athlete_id}:{row['event']}:{row['level']}:{row['score']}"
        record_hash = hashlib.md5(hash_str.encode()).hexdigest()

        existing_score = conn.execute(text(
            "SELECT id FROM scores WHERE record_hash = :h"
        ), {"h": record_hash}).fetchone()
        if existing_score:
            skipped += 1
            continue

        conn.execute(text("""
            INSERT INTO scores (meet_id, athlete_id, event, level, score, place, source, record_hash)
            VALUES (:mid, :aid, :event, :level, :score, :place, 'scorecat', :hash)
        """), {
            "mid":   meet_db_id,
            "aid":   athlete_id,
            "event": row["event"],
            "level": row["level"],
            "score": row["score"] if pd.notna(row["score"]) else None,
            "place": int(row["place"]) if pd.notna(row["place"]) and row["place"] else None,
            "hash":  record_hash,
        })
        inserted += 1

print(f"\nDone. Inserted: {inserted} | Skipped (dupes): {skipped}")
