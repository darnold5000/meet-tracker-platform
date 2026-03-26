-- Remove all cheer MVP rows; keep tables. Postgres.
-- Run: psql "$DATABASE_URL" -f scripts/truncate_cheer_mvp.sql
-- Or use: python scripts/truncate_cheer_mvp.py

TRUNCATE TABLE
  cheer_mvp_performances,
  cheer_mvp_sessions,
  cheer_mvp_meets,
  cheer_mvp_teams
RESTART IDENTITY CASCADE;
