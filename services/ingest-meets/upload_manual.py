#!/usr/bin/env python3
"""
Manual Upload Script for Meet Data

Uploads CSV or JSON files with meet results using the same normalization
and deduplication logic as the automated scrapers.

Usage:
    python upload_manual.py <file_path> [--format csv|json] [--dry-run]

File format: See MANUAL_UPLOAD_FORMAT.md for details
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
load_dotenv()

from core.normalizer import normalize_athlete_name, normalize_level, normalize_event
from core.gym_normalizer import normalize_gym_name as normalize_gym_name_canonical
from db.database import SessionLocal
from db.models import Meet
import logging

# Import ingest functions after argparse setup to avoid conflicts
# (ingest.py has a global parser that conflicts)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger("upload_manual")


def parse_csv_file(file_path: str) -> List[Dict]:
    """Parse CSV file into list of dicts."""
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert empty strings to None
            cleaned = {k: (v.strip() if v and v.strip() else None) for k, v in row.items()}
            rows.append(cleaned)
    return rows


def parse_json_file(file_path: str) -> List[Dict]:
    """Parse JSON file into list of dicts."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON file must contain an array of athlete records")
    return data


def normalize_manual_record(raw: Dict) -> List[Dict]:
    """
    Normalize a manual upload record into the standard format.
    Handles both wide format (one row per athlete) and long format (one row per event).
    
    Returns list of normalized score records (one per event).
    """
    # Extract base fields
    meet_id = raw.get("meet_id") or raw.get("meet_id")
    athlete_name = normalize_athlete_name(raw.get("athlete_name") or raw.get("athlete") or "")
    gym = normalize_gym_name_canonical(raw.get("gym") or raw.get("gym_name") or "")
    level = normalize_level(raw.get("level") or "")
    division = raw.get("division")
    session = raw.get("session")
    source = raw.get("source", "manual")
    
    if not meet_id:
        raise ValueError("Missing required field: meet_id")
    if not athlete_name:
        raise ValueError("Missing required field: athlete_name")
    if not gym:
        raise ValueError("Missing required field: gym")
    if not level:
        raise ValueError("Missing required field: level")
    
    records = []
    
    # Handle wide format: one row per athlete with all scores
    # Check if we have event-specific columns
    event_score_map = {
        "aa": ("AA", "aa_score", "aa_place"),
        "aa_score": ("AA", "aa_score", "aa_place"),
        "vault": ("VT", "vault", "vault_place"),
        "vt": ("VT", "vault", "vt_place"),
        "bars": ("UB", "bars", "bars_place"),
        "ub": ("UB", "bars", "ub_place"),
        "beam": ("BB", "beam", "beam_place"),
        "bb": ("BB", "beam", "bb_place"),
        "floor": ("FX", "floor", "floor_place"),
        "fx": ("FX", "floor", "fx_place"),
    }
    
    # Try to find scores in wide format
    found_events = False
    for event_key, (event_code, score_key, place_key) in event_score_map.items():
        # Try multiple key variations
        score = None
        place = None
        
        # Try exact key match first
        if score_key in raw:
            score = raw[score_key]
        elif event_key in raw:
            score = raw[event_key]
        
        # Try place key variations
        if place_key in raw:
            place = raw[place_key]
        elif f"{event_key}_place" in raw:
            place = raw[f"{event_key}_place"]
        
        # Parse score
        if score is not None:
            try:
                score = float(score) if score else None
            except (ValueError, TypeError):
                score = None
        
        # Parse place (handle ties like "3T")
        if place is not None:
            try:
                if isinstance(place, str):
                    # Extract numeric part from "3T" -> 3
                    import re
                    match = re.match(r'(\d+)', str(place))
                    place = int(match.group(1)) if match else None
                else:
                    place = int(place) if place else None
            except (ValueError, TypeError):
                place = None
        
        if score is not None:
            found_events = True
            records.append({
                "athlete_name": athlete_name,
                "gym": gym,
                "level": level,
                "division": division,
                "meet_id": meet_id,
                "session": session,
                "source": source,
                "event": event_code,
                "score": score,
                "place": place,
            })
    
    # If no events found, check if this is long format (one row per event)
    if not found_events:
        event = normalize_event(raw.get("event") or "")
        score = raw.get("score")
        place = raw.get("place")
        
        if event and score is not None:
            try:
                score = float(score) if score else None
            except (ValueError, TypeError):
                score = None
            
            # Parse place
            if place is not None:
                try:
                    if isinstance(place, str):
                        import re
                        match = re.match(r'(\d+)', str(place))
                        place = int(match.group(1)) if match else None
                    else:
                        place = int(place) if place else None
                except (ValueError, TypeError):
                    place = None
            
            if score is not None:
                records.append({
                    "athlete_name": athlete_name,
                    "gym": gym,
                    "level": level,
                    "division": division,
                    "meet_id": meet_id,
                    "session": session,
                    "source": source,
                    "event": event,
                    "score": score,
                    "place": place,
                })
    
    if not records:
        raise ValueError(f"No valid scores found for athlete {athlete_name}")
    
    return records


def validate_meet_exists(meet_id: str) -> bool:
    """Check if meet exists in database."""
    db = SessionLocal()
    try:
        meet = db.query(Meet).filter(Meet.meet_id == meet_id).first()
        return meet is not None
    finally:
        db.close()


def import_save_scores():
    """Import save_scores function after argparse is set up."""
    # ingest.py calls parser.parse_args() at module level, which conflicts with our args
    # Temporarily modify sys.argv so ingest.py's parser doesn't see our arguments
    import sys
    original_argv = sys.argv[:]
    
    try:
        # Replace argv with minimal args that ingest.py's parser expects
        # ingest.py's parser only has optional args, so empty list should work
        sys.argv = ['ingest.py']
        
        # Now import - ingest.py's parser.parse_args() will use our fake args
        from ingest import save_scores
        return save_scores
    finally:
        # Restore original argv
        sys.argv = original_argv


def main():
    parser = argparse.ArgumentParser(description="Upload manual meet data from CSV or JSON")
    parser.add_argument("file_path", help="Path to CSV or JSON file")
    parser.add_argument("--format", choices=["csv", "json", "auto"], default="auto",
                       help="File format (auto-detect if not specified)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Validate file without importing")
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    
    # Detect format
    if args.format == "auto":
        if file_path.suffix.lower() == ".json":
            file_format = "json"
        elif file_path.suffix.lower() == ".csv":
            file_format = "csv"
        else:
            print(f"ERROR: Cannot auto-detect format for {file_path.suffix}")
            print("Please specify --format csv or --format json")
            sys.exit(1)
    else:
        file_format = args.format
    
    # Parse file
    print(f"Reading {file_format.upper()} file: {file_path}")
    try:
        if file_format == "csv":
            raw_records = parse_csv_file(str(file_path))
        else:
            raw_records = parse_json_file(str(file_path))
    except Exception as e:
        print(f"ERROR: Failed to parse file: {e}")
        sys.exit(1)
    
    print(f"Loaded {len(raw_records)} records")
    
    # Validate meet_ids exist
    meet_ids = set(r.get("meet_id") for r in raw_records if r.get("meet_id"))
    print(f"Found meet IDs: {sorted(meet_ids)}")
    
    for meet_id in meet_ids:
        if not validate_meet_exists(meet_id):
            print(f"ERROR: Meet '{meet_id}' not found in database")
            print("Please create the meet first or check the meet_id spelling")
            sys.exit(1)
    
    # Normalize records
    print("\nNormalizing records...")
    normalized_records = []
    errors = []
    
    for i, raw in enumerate(raw_records, 1):
        try:
            records = normalize_manual_record(raw)
            normalized_records.extend(records)
        except Exception as e:
            errors.append((i, raw.get("athlete_name", "Unknown"), str(e)))
    
    if errors:
        print(f"\n⚠️  {len(errors)} records had errors:")
        for row_num, athlete, error in errors[:10]:  # Show first 10
            print(f"  Row {row_num} ({athlete}): {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    
    if not normalized_records:
        print("ERROR: No valid records to import")
        sys.exit(1)
    
    print(f"Normalized to {len(normalized_records)} score records")
    
    # Group by meet_id
    by_meet = {}
    for record in normalized_records:
        meet_id = record["meet_id"]
        if meet_id not in by_meet:
            by_meet[meet_id] = []
        by_meet[meet_id].append(record)
    
    print(f"\nRecords by meet:")
    for meet_id, records in by_meet.items():
        print(f"  {meet_id}: {len(records)} score records")
    
    # Show sample
    print(f"\nSample normalized record:")
    sample = normalized_records[0]
    print(f"  Athlete: {sample['athlete_name']}")
    print(f"  Gym: {sample['gym']}")
    print(f"  Level: {sample['level']}")
    print(f"  Event: {sample['event']}")
    print(f"  Score: {sample['score']}")
    print(f"  Place: {sample.get('place', 'N/A')}")
    
    if args.dry_run:
        print("\n✅ DRY RUN: File is valid. Run without --dry-run to import.")
        return
    
    # Confirm
    print(f"\nReady to import {len(normalized_records)} score records across {len(by_meet)} meet(s)")
    confirm = input("Continue? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return
    
    # Import save_scores function (after argparse to avoid conflicts)
    save_scores = import_save_scores()
    
    # Import
    print("\nImporting...")
    total_inserted = 0
    total_skipped = 0
    
    for meet_id, records in by_meet.items():
        print(f"\nProcessing meet: {meet_id}")
        inserted, skipped = save_scores(records, meet_id)
        total_inserted += inserted
        total_skipped += skipped
        print(f"  Inserted: {inserted}  |  Skipped (dupes): {skipped}")
    
    print(f"\n{'='*60}")
    print(f"✅ Import complete!")
    print(f"  Total inserted: {total_inserted}")
    print(f"  Total skipped (duplicates): {total_skipped}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
