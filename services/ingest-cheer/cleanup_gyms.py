import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.begin() as conn:
    # Preview gyms to be deleted (no scores associated at all)
    preview = conn.execute(text("""
        SELECT g.id, g.canonical_name,
               COUNT(DISTINCT a.id) AS athlete_count
        FROM gyms g
        LEFT JOIN athletes a ON a.gym_id = g.id
        WHERE NOT EXISTS (
            SELECT 1 FROM athletes a2
            JOIN scores s ON s.athlete_id = a2.id
            WHERE a2.gym_id = g.id
        )
        GROUP BY g.id, g.canonical_name
        ORDER BY g.canonical_name
    """)).fetchall()

    print(f"Gyms with no score records: {len(preview)}")
    for row in preview:
        label = f"{row[2]} scoreless athlete(s)" if row[2] > 0 else "no athletes"
        print(f"  [{row[0]}] {row[1]}  ({label})")

    confirm = input("\nDelete all of these? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Cancelled — no changes made.")
    else:
        gym_ids = [row[0] for row in preview]
        if not gym_ids:
            print("Nothing to delete.")
        else:
            id_list = ','.join(str(i) for i in gym_ids)

            # 1. Delete athlete aliases for any athletes in these gyms
            r1 = conn.execute(text(f"""
                DELETE FROM athlete_aliases
                WHERE athlete_id IN (
                    SELECT id FROM athletes WHERE gym_id IN ({id_list})
                )
            """))
            print(f"  Deleted {r1.rowcount} athlete aliases")

            # 2. Delete athletes in these gyms (only scoreless ones — safety check)
            r2 = conn.execute(text(f"""
                DELETE FROM athletes
                WHERE gym_id IN ({id_list})
                AND NOT EXISTS (SELECT 1 FROM scores WHERE athlete_id = athletes.id)
            """))
            print(f"  Deleted {r2.rowcount} scoreless athletes")

            # 3. Delete the gyms that now have no athletes at all
            r3 = conn.execute(text(f"""
                DELETE FROM gyms
                WHERE id IN ({id_list})
                AND NOT EXISTS (
                    SELECT 1 FROM athletes WHERE gym_id = gyms.id
                )
            """))
            print(f"  Deleted {r3.rowcount} gyms")
            print("\nDone.")
