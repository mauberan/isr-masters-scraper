-- db/indexes.sql
--
-- Performance indexes for isr_masters.
--
-- These are created separately from schema.sql so they can be reasoned
-- about and modified independently. Indexes are an operational concern
-- (performance tuning) not a structural one (schema design).
--
-- Run with:
--   psql postgresql://isr:isr@localhost:5432/isr_masters -f db/indexes.sql

-- -----------------------------------------------------------------------------
-- results — the largest table, most frequently queried
-- -----------------------------------------------------------------------------

-- Most common lookup: all results for a specific swimmer
-- Powers: personal best queries, progression over time, swimmer profiles
CREATE INDEX IF NOT EXISTS idx_results_swimmer
    ON results(swimmer_id);

-- All results within a heat (used when rendering heat sheets)
CREATE INDEX IF NOT EXISTS idx_results_heat
    ON results(heat_id);

-- Partial composite: swimmer + time, only for valid (non-DSQ, non-DNS) results
-- Powers: personal best calculation without filtering in the query itself
-- Smaller than a full index because it excludes ~5-10% of rows
CREATE INDEX IF NOT EXISTS idx_results_swimmer_time_valid
    ON results(swimmer_id, time_ms)
    WHERE time_ms IS NOT NULL
      AND dsq = FALSE
      AND dns = FALSE;

-- -----------------------------------------------------------------------------
-- competitions — filtered by date range for season/year queries
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_competitions_date
    ON competitions(start_date);

-- -----------------------------------------------------------------------------
-- events — filtered by stroke/distance for cross-competition comparisons
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_events_competition
    ON events(competition_id);

-- Useful when querying "all 50m freestyle results across all competitions"
CREATE INDEX IF NOT EXISTS idx_events_stroke_distance
    ON events(stroke, distance_m);

-- -----------------------------------------------------------------------------
-- heats — lookup by event
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_heats_event
    ON heats(event_id);

-- Record migration
INSERT INTO schema_migrations (version)
VALUES ('003_indexes')
ON CONFLICT (version) DO NOTHING;