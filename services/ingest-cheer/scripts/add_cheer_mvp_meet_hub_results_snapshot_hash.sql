-- Idempotent: skip duplicate ALTER if column already exists (run manually or via app ensure).
ALTER TABLE cheer_mvp_meets ADD COLUMN IF NOT EXISTS hub_results_snapshot_hash VARCHAR(64);
