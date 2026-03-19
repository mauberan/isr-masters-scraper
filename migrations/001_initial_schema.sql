-- migrations/001_initial_schema.sql
--
-- Baseline marker. The actual schema is in db/schema.sql and is applied
-- automatically by Docker on first container start
-- (via docker-entrypoint-initdb.d).
--
-- This file exists so schema_migrations has a complete history from the start.

INSERT INTO schema_migrations (version) VALUES ('001_initial_schema');
