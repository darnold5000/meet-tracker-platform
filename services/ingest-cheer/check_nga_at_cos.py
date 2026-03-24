import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT a.canonical_name, s.level, s.event, s.score
        FROM athletes a
        JOIN gyms g ON g.id = a.gym_id
        JOIN scores s ON s.athlete_id = a.id
        JOIN meets m ON m.id = s.meet_id
        WHERE g.canonical_name = 'The Flip Zone'
          AND m.name = '2026 Circle of Stars'
          AND a.id IN (
              SELECT DISTINCT athlete_id
              FROM scores
              WHERE level = 'SN'
          )
        ORDER BY a.canonical_name, s.event
    """)).fetchall()

    if not rows:
        print("No Flip Zone NGA Silver athletes found at Circle of Stars.")
    else:
        print(f"Flip Zone NGA Silver athletes who competed at Circle of Stars: {len(set(r[0] for r in rows))} athletes\n")
        current = None
        for r in rows:
            if r[0] != current:
                current = r[0]
                print(f"\n  {current}")
            print(f"    event={r[2]}  score={r[3]}  stored_level={r[1]}")
