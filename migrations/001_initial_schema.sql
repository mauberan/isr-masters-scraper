-- migrations/001_initial_schema.sql
--
-- Baseline marker. The actual schema is in db/schema.sql and is applied
-- automatically by Docker on first container start
-- (via docker-entrypoint-initdb.d).
--
-- This file exists so the migrations table has a complete history
-- starting from the beginning.

INSERT INTO schema_migrations (version) VALUES ('001_initial_schema');