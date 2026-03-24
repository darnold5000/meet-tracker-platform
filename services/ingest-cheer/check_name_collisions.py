import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Find Flip Zone athletes who share their canonical name with athletes at OTHER gyms
    rows = conn.execute(text("""
        SELECT a.id, a.canonical_name,
               g.canonical_name AS fz_gym,
               array_agg(DISTINCT g2.canonical_name ORDER BY g2.canonical_name) AS other_gyms
        FROM athletes a
        JOIN gyms g ON g.id = a.gym_id
        JOIN athletes a2 ON LOWER(a2.canonical_name) = LOWER(a.canonical_name)
                         AND a2.id != a.id
        JOIN gyms g2 ON g2.id = a2.gym_id
        WHERE g.canonical_name = 'The Flip Zone'
        GROUP BY a.id, a.canonical_name, g.canonical_name
        ORDER BY a.canonical_name
    """)).fetchall()

    if not rows:
        print("No name collisions found for Flip Zone athletes.")
    else:
        print(f"Flip Zone athletes whose name also exists at another gym: {len(rows)}\n")
        print(f"  {'Athlete':<30} Other gyms with same name")
        print(f"  {'-'*75}")
        for r in rows:
            gyms = ", ".join(r[3])
            print(f"  {r[1]:<30} {gyms}")
