-- migrations/006_align_with_models.sql
--
-- Aligns schema with the actual CompetitionDocument shape from models.py.
--
-- Changes:
--   1. Add clubs table
--   2. Add loglig_id + club_id + gender to swimmers
--   3. Add loglig metadata columns to events
--   4. Add score fields (place, points, splits, etc.) to results
--   5. Add relay_results table
--   6. Add loglig_id + sport_type to competitions

-- 1. clubs
CREATE TABLE clubs (
    id        SERIAL PRIMARY KEY,
    loglig_id INT    UNIQUE,
    name      TEXT   NOT NULL UNIQUE
);

-- 2. swimmers
ALTER TABLE swimmers
    ADD COLUMN loglig_id VARCHAR(50) UNIQUE,
    ADD COLUMN club_id   INT REFERENCES clubs(id),
    ADD COLUMN gender    VARCHAR(5);

-- 3. competitions
ALTER TABLE competitions
    ADD COLUMN loglig_id   VARCHAR(50),
    ADD COLUMN sport_type  TEXT;

-- events: drop old name-based unique constraint, add loglig-based one
ALTER TABLE events DROP CONSTRAINT IF EXISTS uq_events_competition_name;
ALTER TABLE events
    ADD COLUMN loglig_event_id VARCHAR(50),
    ADD COLUMN event_num       INT,
    ADD COLUMN category        TEXT,
    ADD COLUMN race_date       DATE,
    ADD COLUMN start_time      VARCHAR(10),
    ADD COLUMN is_relay        BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE events
    ADD CONSTRAINT uq_events_competition_loglig UNIQUE (competition_id, loglig_event_id);

-- 4. results
ALTER TABLE results
    ADD COLUMN club_id       INT REFERENCES clubs(id),
    ADD COLUMN place         INT,
    ADD COLUMN points        INT,
    ADD COLUMN team_points   INT,
    ADD COLUMN reaction_time VARCHAR(20),
    ADD COLUMN splits        JSONB;

-- 5. relay_results
CREATE TABLE relay_results (
    id           SERIAL   PRIMARY KEY,
    heat_id      INT      NOT NULL REFERENCES heats(id) ON DELETE CASCADE,
    club_id      INT      NOT NULL REFERENCES clubs(id),
    swimmer_ids  INT[]    NOT NULL,
    lane         INT,
    time_ms      INT,
    dsq          BOOLEAN  NOT NULL DEFAULT FALSE,
    dns          BOOLEAN  NOT NULL DEFAULT FALSE,
    place        INT,
    points       INT,
    team_points  INT,
    splits       JSONB,
    scraped_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (heat_id, club_id, lane)
);

CREATE INDEX idx_relay_results_heat ON relay_results(heat_id);
CREATE INDEX idx_relay_results_club ON relay_results(club_id);

INSERT INTO schema_migrations (version) VALUES ('006_align_with_models');
