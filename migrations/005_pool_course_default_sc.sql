-- migrations/005_pool_course_default_sc.sql
--
-- Sets pool_course default to SC (short course, 25m pool).
-- All current ISR Masters competitions are short course.

ALTER TABLE competitions
    ALTER COLUMN pool_course SET DEFAULT 'SC';

ALTER TABLE events
    ALTER COLUMN pool_course SET DEFAULT 'SC';

UPDATE competitions SET pool_course = 'SC' WHERE pool_course IS NULL;
UPDATE events       SET pool_course = 'SC' WHERE pool_course IS NULL;

INSERT INTO schema_migrations (version) VALUES ('005_pool_course_default_sc');
