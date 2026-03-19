-- migrations/009_nullable_start_date.sql
--
-- Makes competitions.start_date nullable.
-- The scraper does not always successfully parse the date range
-- (e.g. competitions with dates=[] produce no date_range string).
-- A NULL start_date is preferable to a hard failure.

ALTER TABLE competitions
    ALTER COLUMN start_date DROP NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('009_nullable_start_date');