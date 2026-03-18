# -*- coding: utf-8 -*-
"""
Merge 'Jpac In' gym into 'Jaycie Phelps Athletic Center'.

This script:
1. Moves all athletes from 'Jpac In' to 'Jaycie Phelps Athletic Center'
2. Merges duplicate athletes (same name) by reassigning scores
3. Deletes the 'Jpac In' gym record
"""

import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

# SOURCE_GYM = 'Jpac In'
SOURCE_GYM = 'Jpac'
TARGET_GYM = 'Jaycie Phelps Athletic Center'

with engine.begin() as conn:
    # Find target gym
    target_gym = conn.execute(text("""
        SELECT id, canonical_name FROM gyms WHERE canonical_name = :name
    """), {"name": TARGET_GYM}).fetchone()
    
    if not target_gym:
        print(f"'{TARGET_GYM}' not found - cannot proceed.")
        exit(1)
    
    print(f"Found target gym: '{TARGET_GYM}' (ID: {target_gym[0]})")
    
    # Find source gym to merge
    source_gym = conn.execute(text("""
        SELECT id, canonical_name FROM gyms WHERE canonical_name = :name
    """), {"name": SOURCE_GYM}).fetchone()
    
    if not source_gym:
        print(f"'{SOURCE_GYM}' not found - nothing to merge.")
        exit(0)
    
    if source_gym[0] == target_gym[0]:
        print(f"'{SOURCE_GYM}' is already '{TARGET_GYM}' (same ID) - nothing to do.")
        exit(0)
    
    print(f"Found source gym: '{SOURCE_GYM}' (ID: {source_gym[0]})")
    
    # Count what will move and check for duplicates
    athlete_count = conn.execute(text("""
        SELECT COUNT(*) FROM athletes WHERE gym_id = :id
    """), {"id": source_gym[0]}).scalar()
    
    score_count = conn.execute(text("""
        SELECT COUNT(*) FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        WHERE a.gym_id = :id
    """), {"id": source_gym[0]}).scalar()
    
    # Check for duplicate athletes (same canonical_name already in target gym)
    duplicate_count = conn.execute(text("""
        SELECT COUNT(*) FROM athletes a1
        WHERE a1.gym_id = :source_id
        AND EXISTS (
            SELECT 1 FROM athletes a2
            WHERE a2.canonical_name = a1.canonical_name
            AND a2.gym_id = :target_id
        )
    """), {"source_id": source_gym[0], "target_id": target_gym[0]}).scalar()
    
    print(f"\n'{SOURCE_GYM}' has:")
    print(f"  {athlete_count} athletes")
    print(f"  {score_count} scores")
    if duplicate_count > 0:
        print(f"  ⚠️  {duplicate_count} athletes already exist in '{TARGET_GYM}' (will merge)")
    
    confirm = input(f"\nMerge '{SOURCE_GYM}' into '{TARGET_GYM}'? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
    else:
        # Get all athletes from source gym
        source_athletes = conn.execute(text("""
            SELECT id, canonical_name FROM athletes WHERE gym_id = :id
        """), {"id": source_gym[0]}).fetchall()
        
        athletes_moved = 0
        athletes_merged = 0
        scores_updated = 0
        
        for athlete_id, athlete_name in source_athletes:
            # Check if athlete already exists in target gym
            existing_athlete = conn.execute(text("""
                SELECT id FROM athletes 
                WHERE canonical_name = :name AND gym_id = :gym_id
            """), {"name": athlete_name, "gym_id": target_gym[0]}).fetchone()
            
            if existing_athlete:
                # Athlete already exists - merge scores to existing athlete
                existing_id = existing_athlete[0]
                updated = conn.execute(text("""
                    UPDATE scores SET athlete_id = :existing_id 
                    WHERE athlete_id = :old_id
                """), {"existing_id": existing_id, "old_id": athlete_id}).rowcount
                scores_updated += updated
                
                # Delete athlete aliases first (foreign key constraint)
                conn.execute(text("""
                    DELETE FROM athlete_aliases WHERE athlete_id = :id
                """), {"id": athlete_id})
                
                # Delete the duplicate athlete
                conn.execute(text("""
                    DELETE FROM athletes WHERE id = :id
                """), {"id": athlete_id})
                athletes_merged += 1
                print(f"    Merged '{athlete_name}' (moved {updated} scores to existing athlete)")
            else:
                # Athlete doesn't exist - move to target gym
                conn.execute(text("""
                    UPDATE athletes SET gym_id = :new_id WHERE id = :old_id
                """), {"new_id": target_gym[0], "old_id": athlete_id})
                athletes_moved += 1
        
        print(f"\n  '{SOURCE_GYM}' merge complete:")
        print(f"    {athletes_moved} athletes moved")
        print(f"    {athletes_merged} athletes merged (duplicates removed)")
        print(f"    {scores_updated} scores reassigned to existing athletes")
        
        # Delete the old gym
        conn.execute(text("""
            DELETE FROM gyms WHERE id = :id
        """), {"id": source_gym[0]})
        print(f"    Deleted '{SOURCE_GYM}' gym record")
        
        print(f"\nDone. All data now under '{TARGET_GYM}'.")
