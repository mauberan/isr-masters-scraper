-- migrations/010_nullable_swimmer_fields.sql
--
-- Makes swimmers.birth_year nullable.
-- Relay swimmers and some individual swimmers have no birth_year
-- available in the HTML (e.g. relay team member links have no birth year).

ALTER TABLE swimmers
    ALTER COLUMN birth_year DROP NOT NULL;

INSERT INTO schema_migrations (version) VALUES ('010_nullable_swimmer_fields');