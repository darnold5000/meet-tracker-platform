"""
Calculate and update place values for The Flip Zone (gym_id 718) meets.
Excludes Tulip City which already has place data.
"""
import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine(os.getenv('DATABASE_URL'))

TULIP_CITY_MEET_NAME = "2026 Tulip City Classic"
FLIP_ZONE_GYM_ID = 718

with engine.begin() as conn:
    # Find all meets for The Flip Zone except Tulip City
    meets = conn.execute(text("""
        SELECT DISTINCT m.id, m.name, m.start_date
        FROM meets m
        JOIN scores s ON s.meet_id = m.id
        JOIN athletes a ON a.id = s.athlete_id
        WHERE a.gym_id = :gym_id
        AND m.name != :tulip_city
        ORDER BY m.start_date DESC
    """), {"gym_id": FLIP_ZONE_GYM_ID, "tulip_city": TULIP_CITY_MEET_NAME}).fetchall()
    
    if not meets:
        print("No meets found for The Flip Zone (excluding Tulip City).")
        exit(0)
    
    print(f"Found {len(meets)} meets for The Flip Zone (excluding Tulip City):\n")
    for meet_id, meet_name, start_date in meets:
        print(f"  - {meet_name} (ID: {meet_id}, Date: {start_date})")
    
    confirm = input("\nCalculate and update place values for these meets? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
        exit(0)
    
    total_updated = 0
    
    for meet_id, meet_name, start_date in meets:
        print(f"\nProcessing: {meet_name}")
        
        # Get all scores for this meet from The Flip Zone athletes
        scores_df = pd.read_sql(text("""
            SELECT s.id, s.athlete_id, s.event, s.level, s.score, s.place
            FROM scores s
            JOIN athletes a ON a.id = s.athlete_id
            WHERE s.meet_id = :meet_id
            AND a.gym_id = :gym_id
        """), conn, params={"meet_id": meet_id, "gym_id": FLIP_ZONE_GYM_ID})
        
        if scores_df.empty:
            print(f"  No scores found for this meet.")
            continue
        
        # Group by level and event, then calculate ranks
        # Higher score = better rank (rank 1 is highest)
        scores_df['place_calculated'] = scores_df.groupby(['level', 'event'])['score'].rank(
            method='min', ascending=False
        ).astype(int)
        
        # Only update scores that don't already have a place value
        to_update = scores_df[scores_df['place'].isna() | (scores_df['place'] == 0)]
        
        if to_update.empty:
            print(f"  All scores already have place values.")
            continue
        
        updated_count = 0
        for _, row in to_update.iterrows():
            conn.execute(text("""
                UPDATE scores 
                SET place = :place 
                WHERE id = :score_id
            """), {
                "place": int(row['place_calculated']),
                "score_id": int(row['id'])
            })
            updated_count += 1
        
        total_updated += updated_count
        print(f"  Updated {updated_count} scores with place values.")
    
    print(f"\n✓ Complete! Updated {total_updated} total scores with place values.")
