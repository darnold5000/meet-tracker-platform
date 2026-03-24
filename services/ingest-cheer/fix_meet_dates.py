import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv('DATABASE_URL'))

updates = [
    ('2025 North Pole Classic USAG',           '2025-12-13', 'Indianapolis, IN',  'IN'),
    ('2026 California Grand Invitational',     '2026-01-09', 'Anaheim, CA',        'CA'),
    ('2026 Jaycie Phelps Midwest Showdown',    '2026-01-23', 'French Lick, IN',    'IN'),
    ('2026 Jaycie Phelps Midwest Showdown NGA','2026-01-23', 'French Lick, IN',    'IN'),
    ('2026 Circle of Stars',                   '2026-01-30', 'Indianapolis, IN',   'IN'),
    ('2026 Walk of Fame Classic',              '2026-02-07', 'Fort Wayne, IN',     'IN'),
    ('2026 Flip For Your Cause [USAG]',        '2026-02-20', 'Westfield, IN',      'IN'),
    ('2026 Flip For Your Cause [NGA]',         '2026-02-20', 'Westfield, IN',      'IN'),
    ('2026 Shamrock Shenanigans At Midwest',   '2026-02-27', 'Dyer, IN',           'IN'),
    ('2025 Bug Bite Invitational',             '2025-11-15', 'Bloomington, IN',    'IN'),
    ('2026 Tulip City Classic',                '2026-02-07', 'Holland, MI',        'MI'),
    ('2026 Derby Classic',                     '2026-02-27', 'Louisville, KY',     'KY'),
    ('2026 Swing Into Spring Invitational',    '2026-02-27', 'West Chester, OH',   'OH'),
]

with engine.begin() as conn:
    for name, date, loc, state in updates:
        result = conn.execute(text(
            "UPDATE meets SET start_date = :d, location = :l, state = :s "
            "WHERE name = :n AND (start_date IS NULL OR location IS NULL)"
        ), {'n': name, 'd': date, 'l': loc, 's': state})
        print(f"  {result.rowcount} row(s) updated: {name}")

print("\nDone.")
