-- Idempotent: performance-level row identity hash for incremental Varsity ingest.
ALTER TABLE cheer_mvp_performances ADD COLUMN IF NOT EXISTS source_row_hash VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_cheer_mvp_perf_source_row_hash
  ON cheer_mvp_performances (source_row_hash)
  WHERE source_row_hash IS NOT NULL;
