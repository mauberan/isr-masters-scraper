-- migrations/004_add_pool_course.sql
--
-- Adds pool_course to events to distinguish short course (SC, 25m pool)
-- from long course (LC, 50m pool).
--
-- Times between SC and LC are not comparable — this column ensures
-- personal bests and rankings are always calculated within the same
-- course type.
--
-- Existing rows default to NULL (unknown). The scraper should populate
-- this from competition metadata going forward.

ALTER TABLE events
    ADD COLUMN pool_course VARCHAR(2)
    CHECK (pool_course IN ('SC', 'LC'));

-- Also add to competitions — usually the entire meet is one course type,
-- which lets us derive it for events that don't specify individually.
ALTER TABLE competitions
    ADD COLUMN pool_course VARCHAR(2)
    CHECK (pool_course IN ('SC', 'LC'));

INSERT INTO schema_migrations (version) VALUES ('004_add_pool_course');