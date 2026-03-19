-- migrations/008_fix_start_time_length.sql
--
-- start_time stores the full datetime string from the scraper
-- e.g. "01/01/2026 09:00:00" (19 chars) not just "09:00:00".
-- VARCHAR(10) was too short.

ALTER TABLE events ALTER COLUMN start_time TYPE TEXT;

INSERT INTO schema_migrations (version) VALUES ('008_fix_start_time_length');