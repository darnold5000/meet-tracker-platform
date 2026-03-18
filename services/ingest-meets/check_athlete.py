import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

name = "Olivia Smith"

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT a.id, a.canonical_name, g.canonical_name AS gym,
               s.level, s.event, s.score, m.name AS meet, m.start_date, m.location
        FROM athletes a
        LEFT JOIN gyms g ON g.id = a.gym_id
        JOIN scores s ON s.athlete_id = a.id
        JOIN meets m ON m.id = s.meet_id
        WHERE LOWER(a.canonical_name) = LOWER(:name)
        ORDER BY m.start_date, s.event
    """), {"name": name}).fetchall()

    if not rows:
        print(f"No scores found for '{name}'")
    else:
        print(f"Athlete: {rows[0][1]}  |  Gym: {rows[0][2]}  |  ID: {rows[0][0]}")
        print(f"{'Meet':<45} {'Date':<12} {'Level':<10} {'Event':<6} Score")
        print("-" * 90)
        for r in rows:
            print(f"{str(r[6]):<45} {str(r[7]):<12} {str(r[3]):<10} {str(r[4]):<6} {r[5]}")
