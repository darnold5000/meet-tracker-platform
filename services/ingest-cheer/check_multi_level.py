import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT a.id, a.canonical_name, g.canonical_name AS gym,
               array_agg(DISTINCT s.level ORDER BY s.level) AS levels,
               COUNT(DISTINCT s.level) AS level_count
        FROM athletes a
        JOIN gyms g ON g.id = a.gym_id
        JOIN scores s ON s.athlete_id = a.id
        WHERE g.canonical_name = 'The Flip Zone'
        GROUP BY a.id, a.canonical_name, g.canonical_name
        HAVING COUNT(DISTINCT s.level) > 1
        ORDER BY COUNT(DISTINCT s.level) DESC, a.canonical_name
    """)).fetchall()

    if not rows:
        print("No Flip Zone athletes with multiple levels found.")
    else:
        print(f"Flip Zone athletes with multiple levels: {len(rows)}\n")
        print(f"  {'Athlete':<30} {'ID':<6} Levels")
        print(f"  {'-'*65}")
        for r in rows:
            print(f"  {r[1]:<30} {r[0]:<6} {r[3]}")

        # For each, show the full meet-by-meet level breakdown
        print(f"\n\n{'='*70}")
        print("Meet-by-meet breakdown:")
        print(f"{'='*70}")
        for r in rows:
            history = conn.execute(text("""
                SELECT MIN(s.level) AS level, m.name, m.start_date
                FROM scores s
                JOIN meets m ON m.id = s.meet_id
                WHERE s.athlete_id = :aid
                GROUP BY m.name, m.start_date
                ORDER BY m.start_date NULLS LAST
            """), {"aid": r[0]}).fetchall()

            print(f"\n  {r[1]} (ID: {r[0]})")
            for h in history:
                print(f"    {str(h[2]):<12} {str(h[1]):<45} Level: {h[0]}")
