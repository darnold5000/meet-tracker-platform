-- Remove standalone calendar year 2026 from cheer_mvp_meets.name (Postgres).
-- Does not touch digits inside longer numbers (e.g. 120268).
-- Run: psql "$DATABASE_URL" -f scripts/strip_2026_from_cheer_mvp_meet_names.sql
--
-- Preview:
--   SELECT meet_key, name AS before,
--          LEFT(BTRIM(REGEXP_REPLACE(REGEXP_REPLACE(name, '(^|[^0-9])2026([^0-9]|$)', '\1\2', 'g'), '\s+', ' ', 'g')), 255) AS after
--   FROM cheer_mvp_meets
--   WHERE name ~ '(^|[^0-9])2026([^0-9]|$)';

BEGIN;

UPDATE cheer_mvp_meets
SET name = LEFT(
  COALESCE(
    NULLIF(
      BTRIM(
        REGEXP_REPLACE(
          REGEXP_REPLACE(name, '(^|[^0-9])2026([^0-9]|$)', '\1\2', 'g'),
          '\s+',
          ' ',
          'g'
        )
      ),
      ''
    ),
    meet_key
  ),
  255
)
WHERE name ~ '(^|[^0-9])2026([^0-9]|$)';

COMMIT;
