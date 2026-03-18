-- migrations/002_unique_constraints_for_upserts.sql
--
-- Adds UNIQUE constraints required by the upsert patterns in db/writer.py.
-- These were omitted from the initial schema and are added as a migration
-- rather than editing 001 — so the history stays honest.

-- Event names are unique within a competition
ALTER TABLE events
    ADD CONSTRAINT uq_events_competition_name UNIQUE (competition_id, name);

-- A heat number is unique within an event
ALTER TABLE heats
    ADD CONSTRAINT uq_heats_event_num UNIQUE (event_id, heat_num);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES ('002_unique_constraints_for_upserts');