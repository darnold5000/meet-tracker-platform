-- Optional: run in Supabase SQL editor if you do not call ``create_tables()`` from ingest-cheer.
-- Varsity-style breakdown: RS/PS; ES is stored as final_score; DED as deductions.

ALTER TABLE cheer_mvp_performances ADD COLUMN IF NOT EXISTS raw_score DOUBLE PRECISION;
ALTER TABLE cheer_mvp_performances ADD COLUMN IF NOT EXISTS performance_score DOUBLE PRECISION;
