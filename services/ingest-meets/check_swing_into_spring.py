import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Check if the meet exists and how many scores it has
    rows = conn.execute(text("""
        SELECT m.id, m.meet_id, m.name, m.start_date, m.location,
               COUNT(s.id) AS score_count,
               COUNT(DISTINCT s.athlete_id) AS athlete_count
        FROM meets m
        LEFT JOIN scores s ON s.meet_id = m.id
        WHERE LOWER(m.name) LIKE '%swing%'
        GROUP BY m.id, m.meet_id, m.name, m.start_date, m.location
    """)).fetchall()

    if not rows:
        print("No meet found matching 'swing' in the database.")
    else:
        for r in rows:
            print(f"Meet:     {r[2]}")
            print(f"ID:       {r[0]}  |  meet_id: {r[1]}")
            print(f"Date:     {r[3]}  |  Location: {r[4]}")
            print(f"Scores:   {r[5]}  |  Athletes: {r[6]}")

    # Also check Flip Zone athletes at this meet if it exists
    fz = conn.execute(text("""
        SELECT a.canonical_name, s.level, s.event, s.score
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        JOIN gyms g ON g.id = a.gym_id
        JOIN meets m ON m.id = s.meet_id
        WHERE LOWER(m.name) LIKE '%swing%'
          AND g.canonical_name = 'The Flip Zone'
        ORDER BY a.canonical_name, s.event
    """)).fetchall()

    if fz:
        print(f"\nFlip Zone athletes at this meet:")
        current = None
        for r in fz:
            if r[0] != current:
                current = r[0]
                print(f"\n  {current}  [Level: {r[1]}]")
            print(f"    {r[2]:<6} {r[3]}")
    else:
        print("\nNo Flip Zone athletes found at this meet.")
