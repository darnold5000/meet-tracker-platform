"""
Database Reset Script — Nuke and Recreate

WARNING: This will delete ALL data from the database!
Use this when you want to start fresh with the new API scraper that includes placement data.
"""
import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text, inspect

engine = create_engine(os.getenv('DATABASE_URL'))

# Get all table names
inspector = inspect(engine)
tables = inspector.get_table_names()

print("=" * 60)
print("  DATABASE RESET — NUKE ALL TABLES")
print("=" * 60)
print(f"\nFound {len(tables)} tables:")
for table in tables:
    print(f"  - {table}")

confirm = input("\n⚠️  WARNING: This will DELETE ALL DATA from the database!\nType 'NUKE' to confirm: ").strip()

if confirm != 'NUKE':
    print("Cancelled. Database unchanged.")
    exit(0)

print("\nDropping all tables...")

with engine.begin() as conn:
    # Drop all tables (in reverse dependency order)
    # Disable foreign key checks temporarily
    conn.execute(text("SET session_replication_role = 'replica';"))
    
    for table in tables:
        try:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
            print(f"  ✓ Dropped {table}")
        except Exception as e:
            print(f"  ✗ Error dropping {table}: {e}")
    
    conn.execute(text("SET session_replication_role = 'origin';"))

print("\nRecreating tables...")

# Import and create tables
from db.database import create_tables
create_tables()

print("\n✓ Database reset complete!")
print("  All tables have been dropped and recreated.")
print("  You can now run ingest.py to populate with new data.")
