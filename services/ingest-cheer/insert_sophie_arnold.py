# -*- coding: utf-8 -*-
"""
Insert Sophie Arnold from The Flip Zone into the athletes table.

This script will:
1. Check if Sophie Arnold already exists
2. Get The Flip Zone gym
3. Insert her if she doesn't exist
4. Optionally make her ID=1 (if ID=1 is available or can be reassigned)

Related tables that may need updates:
- athletes (main table)
- athlete_aliases (if she has name variations)
- scores (if she has competition scores - these link via athlete_id)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from db.models import Athlete, Gym, AthleteAlias
from core.normalizer import normalize_athlete_name
from core.gym_normalizer import normalize_gym_name as normalize_gym_name_canonical

ATHLETE_NAME = "Sophie Arnold"
GYM_NAME = "The Flip Zone"


def get_or_create_gym(engine):
    """Get The Flip Zone gym or create it if it doesn't exist."""
    with engine.begin() as conn:
        # Check if gym exists
        gym = conn.execute(text("""
            SELECT id, canonical_name FROM gyms 
            WHERE canonical_name = 'The Flip Zone'
        """)).fetchone()
        
        if gym:
            gym_id = gym[0]
            print(f"[OK] Found gym: '{gym[1]}' (ID: {gym_id})")
            return gym_id
        
        # Create the gym if it doesn't exist
        print(f"[INFO] 'The Flip Zone' gym not found - creating it...")
        result = conn.execute(text("""
            INSERT INTO gyms (name, canonical_name, created_at)
            VALUES (:name, :canonical_name, :created_at)
            RETURNING id, canonical_name
        """), {
            "name": "The Flip Zone",
            "canonical_name": "The Flip Zone",
            "created_at": datetime.utcnow()
        })
        new_gym = result.fetchone()
        gym_id = new_gym[0]
        print(f"[OK] Created gym: '{new_gym[1]}' (ID: {gym_id})")
        return gym_id


def check_current_state(engine, gym_id):
    """Check if Sophie Arnold already exists and current ID state."""
    with engine.connect() as conn:
        
        # Check if Sophie Arnold exists
        athlete = conn.execute(text("""
            SELECT id, canonical_name, gym_id, level, created_at
            FROM athletes
            WHERE canonical_name = :name AND gym_id = :gym_id
        """), {"name": ATHLETE_NAME, "gym_id": gym_id}).fetchone()
        
        if athlete:
            print(f"[OK] Sophie Arnold already exists:")
            print(f"   ID: {athlete[0]}")
            print(f"   Name: {athlete[1]}")
            print(f"   Gym ID: {athlete[2]}")
            print(f"   Level: {athlete[3]}")
            print(f"   Created: {athlete[4]}")
            
            # Check for aliases
            aliases = conn.execute(text("""
                SELECT raw_name, source FROM athlete_aliases
                WHERE athlete_id = :athlete_id
            """), {"athlete_id": athlete[0]}).fetchall()
            
            if aliases:
                print(f"   Aliases: {', '.join([a[0] for a in aliases])}")
            
            # Check for scores
            score_count = conn.execute(text("""
                SELECT COUNT(*) FROM scores WHERE athlete_id = :athlete_id
            """), {"athlete_id": athlete[0]}).fetchone()[0]
            
            print(f"   Scores: {score_count} records")
            
            return athlete[0], athlete
        else:
            print(f"[INFO] Sophie Arnold not found - will create new record")
            
            # Check current ID=1 status
            id_one = conn.execute(text("""
                SELECT id, canonical_name FROM athletes WHERE id = 1
            """)).fetchone()
            
            if id_one:
                print(f"[WARN] ID=1 is currently occupied by: {id_one[1]}")
            else:
                print(f"[OK] ID=1 is available")
            
            return None, None


def get_next_id(engine):
    """Get the next available athlete ID."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT MAX(id) FROM athletes
        """)).fetchone()
        max_id = result[0] if result[0] else 0
        return max_id + 1


def insert_sophie_as_first(engine, gym_id, make_id_one=False):
    """
    Insert Sophie Arnold, optionally making her ID=1.
    
    Args:
        engine: Database engine
        gym_id: The Flip Zone gym ID
        make_id_one: If True, will attempt to make her ID=1 (requires ID=1 to be available or reassignment)
    """
    normalized_name = normalize_athlete_name(ATHLETE_NAME)
    
    with engine.begin() as conn:
        if make_id_one:
            # Check if ID=1 is available
            id_one_athlete = conn.execute(text("""
                SELECT id, canonical_name FROM athletes WHERE id = 1
            """)).fetchone()
            
            if id_one_athlete:
                print(f"\n[WARN] ID=1 is currently occupied by: {id_one_athlete[1]}")
                response = input("Do you want to reassign ID=1? This will swap IDs. (yes/no): ").strip().lower()
                
                if response == "yes":
                    # Get Sophie's new ID first
                    next_id = get_next_id(engine)
                    print(f"   Will insert Sophie with ID={next_id}, then swap with ID=1")
                    
                    # Insert Sophie with next available ID
                    conn.execute(text("""
                        INSERT INTO athletes (id, canonical_name, gym_id, created_at)
                        VALUES (:id, :name, :gym_id, :created_at)
                    """), {
                        "id": next_id,
                        "name": normalized_name,
                        "gym_id": gym_id,
                        "created_at": datetime.utcnow()
                    })
                    
                    # Swap IDs: temporarily use a high ID, then swap
                    temp_id = next_id + 100000  # Use a very high temp ID to avoid conflicts
                    old_id_one_name = id_one_athlete[1]
                    
                    # Step 1: Move current ID=1's foreign keys to temp
                    print("   Updating foreign keys in related tables...")
                    conn.execute(text("""
                        UPDATE scores SET athlete_id = :temp_id WHERE athlete_id = 1
                    """), {"temp_id": temp_id})
                    conn.execute(text("""
                        UPDATE athlete_aliases SET athlete_id = :temp_id WHERE athlete_id = 1
                    """), {"temp_id": temp_id})
                    
                    # Step 2: Move Sophie's foreign keys (from next_id) to ID=1
                    # (Sophie doesn't have any yet, but this ensures consistency)
                    conn.execute(text("""
                        UPDATE scores SET athlete_id = 1 WHERE athlete_id = :next_id
                    """), {"next_id": next_id})
                    conn.execute(text("""
                        UPDATE athlete_aliases SET athlete_id = 1 WHERE athlete_id = :next_id
                    """), {"next_id": next_id})
                    
                    # Step 3: Swap athlete IDs
                    conn.execute(text("""
                        UPDATE athletes SET id = :temp_id WHERE id = 1
                    """), {"temp_id": temp_id})
                    conn.execute(text("""
                        UPDATE athletes SET id = 1 WHERE id = :next_id
                    """), {"next_id": next_id})
                    conn.execute(text("""
                        UPDATE athletes SET id = :next_id WHERE id = :temp_id
                    """), {"next_id": next_id, "temp_id": temp_id})
                    
                    # Step 4: Move old ID=1's foreign keys from temp to next_id
                    conn.execute(text("""
                        UPDATE scores SET athlete_id = :next_id WHERE athlete_id = :temp_id
                    """), {"next_id": next_id, "temp_id": temp_id})
                    conn.execute(text("""
                        UPDATE athlete_aliases SET athlete_id = :next_id WHERE athlete_id = :temp_id
                    """), {"next_id": next_id, "temp_id": temp_id})
                    
                    # Reset sequence if using PostgreSQL (Supabase)
                    # This ensures future auto-increments don't conflict
                    try:
                        conn.execute(text("""
                            SELECT setval('athletes_id_seq', (SELECT MAX(id) FROM athletes))
                        """))
                    except Exception:
                        # Not PostgreSQL or sequence doesn't exist - that's okay
                        pass
                    
                    print(f"[OK] Sophie Arnold inserted with ID=1")
                    print(f"   Previous ID=1 athlete ({old_id_one_name}) now has ID={next_id}")
                    return 1
                else:
                    print("   Skipping ID reassignment - will insert with next available ID")
                    make_id_one = False
        
        if not make_id_one:
            # Regular insert - let database assign next ID
            result = conn.execute(text("""
                INSERT INTO athletes (canonical_name, gym_id, created_at)
                VALUES (:name, :gym_id, :created_at)
                RETURNING id
            """), {
                "name": normalized_name,
                "gym_id": gym_id,
                "created_at": datetime.utcnow()
            })
            new_id = result.fetchone()[0]
            print(f"[OK] Sophie Arnold inserted with ID={new_id}")
            return new_id
        
        # If make_id_one=True and ID=1 was available
        conn.execute(text("""
            INSERT INTO athletes (id, canonical_name, gym_id, created_at)
            VALUES (1, :name, :gym_id, :created_at)
        """), {
            "name": normalized_name,
            "gym_id": gym_id,
            "created_at": datetime.utcnow()
        })
        
        # Reset sequence if using PostgreSQL (Supabase)
        # This ensures future auto-increments don't conflict
        try:
            conn.execute(text("""
                SELECT setval('athletes_id_seq', (SELECT MAX(id) FROM athletes))
            """))
        except Exception:
            # Not PostgreSQL or sequence doesn't exist - that's okay
            pass
        
        print(f"[OK] Sophie Arnold inserted with ID=1")
        return 1


def create_alias(engine, athlete_id, raw_name="Sophie Arnold", source="manual"):
    """Create an athlete alias entry."""
    with engine.begin() as conn:
        # Check if alias already exists
        existing = conn.execute(text("""
            SELECT id FROM athlete_aliases
            WHERE athlete_id = :athlete_id AND raw_name = :raw_name
        """), {"athlete_id": athlete_id, "raw_name": raw_name}).fetchone()
        
        if existing:
            print(f"   Alias '{raw_name}' already exists")
            return
        
        conn.execute(text("""
            INSERT INTO athlete_aliases (athlete_id, raw_name, source)
            VALUES (:athlete_id, :raw_name, :source)
        """), {
            "athlete_id": athlete_id,
            "raw_name": raw_name,
            "source": source
        })
        print(f"[OK] Created alias: '{raw_name}'")


def main():
    """Main execution."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL not found in environment")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    print("=" * 70)
    print("Insert Sophie Arnold from The Flip Zone")
    print("=" * 70)
    print()
    
    # Get or create The Flip Zone gym
    gym_id = get_or_create_gym(engine)
    print()
    
    # Check current state
    existing_athlete_id, athlete_info = check_current_state(engine, gym_id)
    
    if existing_athlete_id:
        print("\n[OK] Sophie Arnold already exists in the database")
        print("\nIf you want to make her ID=1, you'll need to manually reassign IDs.")
        print("This is a complex operation that affects related tables:")
        print("  - scores (athlete_id foreign key)")
        print("  - athlete_aliases (athlete_id foreign key)")
        return
    
    print("\n" + "=" * 70)
    print("Insertion Options:")
    print("=" * 70)
    print("1. Insert with next available ID (safest)")
    print("2. Insert with ID=1 (if available)")
    print("3. Insert with ID=1 and reassign current ID=1 (complex)")
    print()
    
    choice = input("Choose option (1/2/3) [default: 1]: ").strip() or "1"
    
    if choice == "1":
        athlete_id = insert_sophie_as_first(engine, gym_id, make_id_one=False)
    elif choice == "2":
        athlete_id = insert_sophie_as_first(engine, gym_id, make_id_one=True)
    elif choice == "3":
        athlete_id = insert_sophie_as_first(engine, gym_id, make_id_one=True)
    else:
        print("Invalid choice, using option 1")
        athlete_id = insert_sophie_as_first(engine, gym_id, make_id_one=False)
    
    # Create alias entry
    print("\nCreating alias entry...")
    create_alias(engine, athlete_id, ATHLETE_NAME, source="manual")
    
    # Verify insertion
    print("\n" + "=" * 70)
    print("Verification:")
    print("=" * 70)
    with engine.connect() as conn:
        athlete = conn.execute(text("""
            SELECT id, canonical_name, gym_id, level, created_at
            FROM athletes
            WHERE id = :id
        """), {"id": athlete_id}).fetchone()
        
        if athlete:
            print(f"[OK] Successfully inserted:")
            print(f"   ID: {athlete[0]}")
            print(f"   Name: {athlete[1]}")
            print(f"   Gym ID: {athlete[2]}")
            print(f"   Level: {athlete[3]}")
            print(f"   Created: {athlete[4]}")
            
            # Show related records
            alias_count = conn.execute(text("""
                SELECT COUNT(*) FROM athlete_aliases WHERE athlete_id = :id
            """), {"id": athlete_id}).fetchone()[0]
            print(f"   Aliases: {alias_count}")
            
            score_count = conn.execute(text("""
                SELECT COUNT(*) FROM scores WHERE athlete_id = :id
            """), {"id": athlete_id}).fetchone()[0]
            print(f"   Scores: {score_count}")
        else:
            print("[ERROR] Could not verify insertion")
    
    print("\n" + "=" * 70)
    print("Related Tables Status:")
    print("=" * 70)
    print("[OK] athletes - Sophie Arnold inserted")
    print("[OK] athlete_aliases - Alias created")
    print("[INFO] scores - No scores yet (will be created when meet data is ingested)")
    print()
    print("Note: When scores are ingested for Sophie Arnold, they will automatically")
    print("      link to her athlete record via athlete_id foreign key.")


if __name__ == "__main__":
    main()
