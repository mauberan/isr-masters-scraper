-- migrations/004_add_pool_course.sql
--
-- Adds pool_course to distinguish short course (SC, 25m pool)
-- from long course (LC, 50m pool). Times between SC and LC are not comparable.

ALTER TABLE competitions
    ADD COLUMN pool_course VARCHAR(2) CHECK (pool_course IN ('SC', 'LC'));

ALTER TABLE events
    ADD COLUMN pool_course VARCHAR(2) CHECK (pool_course IN ('SC', 'LC'));

INSERT INTO schema_migrations (version) VALUES ('004_add_pool_course');
