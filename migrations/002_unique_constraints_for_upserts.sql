-- migrations/002_unique_constraints_for_upserts.sql
--
-- Adds UNIQUE constraints required by upsert patterns in db/writer.py.

ALTER TABLE events
    ADD CONSTRAINT uq_events_competition_name UNIQUE (competition_id, name);

ALTER TABLE heats
    ADD CONSTRAINT uq_heats_event_num UNIQUE (event_id, heat_num);

INSERT INTO schema_migrations (version) VALUES ('002_unique_constraints_for_upserts');
