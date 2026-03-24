import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")

engine = create_engine(os.getenv("DATABASE_URL"))

with engine.begin() as conn:

    duplicates = conn.execute(text("""
        SELECT canonical_name, level, gym_id, COUNT(*) AS num_duplicates
        FROM athletes
        WHERE gym_id IS NOT NULL
        GROUP BY canonical_name, level, gym_id
        HAVING COUNT(*) > 1
        ORDER BY canonical_name, level
    """)).fetchall()

    if not duplicates:
        print("No duplicate athletes found.")
        exit(0)

    print("Found", len(duplicates), "groups of duplicate athletes:\n")

    for canonical_name, level, gym_id, num_dup in duplicates:
        print(" ", canonical_name, "(Level", level, ", Gym ID", gym_id, "):", num_dup, "duplicates")

    confirm = input("\nMerge duplicate athletes? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        exit(0)

    athletes_merged = 0
    scores_moved = 0
    aliases_moved = 0

    for canonical_name, level, gym_id, num_dup in duplicates:

        athlete_data = conn.execute(text("""
            SELECT a.id, COUNT(s.id) AS score_count
            FROM athletes a
            LEFT JOIN scores s ON s.athlete_id = a.id
            WHERE a.canonical_name = :name AND a.level = :level AND a.gym_id = :gym_id
            GROUP BY a.id
            ORDER BY score_count DESC, a.id
        """), {"name": canonical_name, "level": level, "gym_id": gym_id}).fetchall()

        if len(athlete_data) < 2:
            continue

        keep_id = athlete_data[0][0]
        merge_ids = [row[0] for row in athlete_data[1:]]

        for merge_id in merge_ids:

            score_count = conn.execute(text("""
                SELECT COUNT(*) FROM scores WHERE athlete_id = :id
            """), {"id": merge_id}).scalar()

            if score_count > 0:
                conn.execute(text("""
                    UPDATE scores
                    SET athlete_id = :keep_id
                    WHERE athlete_id = :merge_id
                """), {"keep_id": keep_id, "merge_id": merge_id})

                scores_moved += score_count

            merge_aliases = conn.execute(text("""
                SELECT raw_name, source
                FROM athlete_aliases
                WHERE athlete_id = :id
            """), {"id": merge_id}).fetchall()

            existing_aliases = set(row[0] for row in conn.execute(text("""
                SELECT raw_name
                FROM athlete_aliases
                WHERE athlete_id = :id
            """), {"id": keep_id}).fetchall())

            for alias_name, source in merge_aliases:

                if alias_name not in existing_aliases:
                    try:
                        conn.execute(text("""
                            INSERT INTO athlete_aliases (athlete_id, raw_name, source)
                            VALUES (:keep_id, :name, :source)
                        """), {
                            "keep_id": keep_id,
                            "name": alias_name,
                            "source": source
                        })

                        aliases_moved += 1
                        existing_aliases.add(alias_name)

                    except Exception:
                        pass

            conn.execute(text("""
                DELETE FROM athlete_aliases
                WHERE athlete_id = :id
            """), {"id": merge_id})

            conn.execute(text("""
                DELETE FROM athletes
                WHERE id = :id
            """), {"id": merge_id})

            athletes_merged += 1

        print("Merged", num_dup - 1, "duplicate(s) for", canonical_name, "(Level", level, ")")

    print("\nMerge complete:")
    print(" ", athletes_merged, "duplicate athletes removed")
    print(" ", scores_moved, "scores reassigned")
    print(" ", aliases_moved, "aliases moved")