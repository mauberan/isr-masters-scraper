-- migrations/003_indexes.sql
-- See db/indexes.sql for full rationale.

CREATE INDEX IF NOT EXISTS idx_results_swimmer            ON results(swimmer_id);
CREATE INDEX IF NOT EXISTS idx_results_heat               ON results(heat_id);
CREATE INDEX IF NOT EXISTS idx_results_swimmer_time_valid ON results(swimmer_id, time_ms)
    WHERE time_ms IS NOT NULL AND dsq = FALSE AND dns = FALSE;
CREATE INDEX IF NOT EXISTS idx_competitions_date          ON competitions(start_date);
CREATE INDEX IF NOT EXISTS idx_events_competition         ON events(competition_id);
CREATE INDEX IF NOT EXISTS idx_events_stroke_distance     ON events(stroke, distance_m);
CREATE INDEX IF NOT EXISTS idx_heats_event                ON heats(event_id);

INSERT INTO schema_migrations (version) VALUES ('003_indexes');
