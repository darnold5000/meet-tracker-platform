import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.begin() as conn:
    # Find target gym
    target_gym = conn.execute(text("""
        SELECT id, canonical_name FROM gyms WHERE canonical_name = 'The Flip Zone'
    """)).fetchone()
    
    if not target_gym:
        print("'The Flip Zone' not found — cannot proceed.")
        exit(1)
    
    print(f"Found target gym: 'The Flip Zone' (ID: {target_gym[0]})")
    
    # Find source gyms to merge
    tfz = conn.execute(text("""
        SELECT id, canonical_name FROM gyms WHERE canonical_name = 'Tfz'
    """)).fetchone()
    
    tfz_in = conn.execute(text("""
        SELECT id, canonical_name FROM gyms WHERE canonical_name = 'Tfz In'
    """)).fetchone()
    
    gyms_to_merge = []
    
    if tfz:
        if tfz[0] == target_gym[0]:
            print("'Tfz' is already 'The Flip Zone' (same ID) — skipping.")
        else:
            gyms_to_merge.append(('Tfz', tfz[0]))
            print(f"Found 'Tfz' (ID: {tfz[0]})")
    else:
        print("'Tfz' not found.")
    
    if tfz_in:
        if tfz_in[0] == target_gym[0]:
            print("'Tfz In' is already 'The Flip Zone' (same ID) — skipping.")
        else:
            gyms_to_merge.append(('Tfz In', tfz_in[0]))
            print(f"Found 'Tfz In' (ID: {tfz_in[0]})")
    else:
        print("'Tfz In' not found.")
    
    if not gyms_to_merge:
        print("\nNo gyms to merge — all data already under 'The Flip Zone'.")
        exit(0)
    
    # Count what will move and check for duplicates
    total_athletes = 0
    total_scores = 0
    total_duplicates = 0
    
    for gym_name, gym_id in gyms_to_merge:
        athlete_count = conn.execute(text("""
            SELECT COUNT(*) FROM athletes WHERE gym_id = :id
        """), {"id": gym_id}).scalar()
        
        score_count = conn.execute(text("""
            SELECT COUNT(*) FROM scores s
            JOIN athletes a ON a.id = s.athlete_id
            WHERE a.gym_id = :id
        """), {"id": gym_id}).scalar()
        
        # Check for duplicate athletes (same canonical_name already in target gym)
        duplicate_count = conn.execute(text("""
            SELECT COUNT(*) FROM athletes a1
            WHERE a1.gym_id = :source_id
            AND EXISTS (
                SELECT 1 FROM athletes a2
                WHERE a2.canonical_name = a1.canonical_name
                AND a2.gym_id = :target_id
            )
        """), {"source_id": gym_id, "target_id": target_gym[0]}).scalar()
        
        total_athletes += athlete_count
        total_scores += score_count
        total_duplicates += duplicate_count
        
        print(f"\n'{gym_name}' has:")
        print(f"  {athlete_count} athletes")
        print(f"  {score_count} scores")
        if duplicate_count > 0:
            print(f"  ⚠️  {duplicate_count} athletes already exist in 'The Flip Zone' (will merge)")
    
    print(f"\nTotal to process:")
    print(f"  {total_athletes} athletes")
    print(f"  {total_scores} scores")
    if total_duplicates > 0:
        print(f"  ⚠️  {total_duplicates} duplicate athletes will be merged (scores reassigned)")
    
    gym_names_str = "', '".join([name for name, _ in gyms_to_merge])
    confirm = input(f"\nMerge '{gym_names_str}' into 'The Flip Zone'? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
    else:
        # Merge each gym
        for gym_name, gym_id in gyms_to_merge:
            # Get all athletes from source gym
            source_athletes = conn.execute(text("""
                SELECT id, canonical_name FROM athletes WHERE gym_id = :id
            """), {"id": gym_id}).fetchall()
            
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
            
            print(f"\n  '{gym_name}' merge complete:")
            print(f"    {athletes_moved} athletes moved")
            print(f"    {athletes_merged} athletes merged (duplicates removed)")
            print(f"    {scores_updated} scores reassigned to existing athletes")
            
            # Delete the old gym
            conn.execute(text("""
                DELETE FROM gyms WHERE id = :id
            """), {"id": gym_id})
            print(f"    Deleted '{gym_name}' gym record")
        
        print("\nDone. All data now under 'The Flip Zone'.")
