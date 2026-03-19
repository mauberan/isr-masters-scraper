-- =============================================================================
-- ISR Masters Scraper — Schema (current state)
-- =============================================================================
-- This file reflects the CURRENT intended schema for a fresh database.
-- Applied automatically by Docker on first container start.
-- For changes to an existing database, see migrations/.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- competitions
-- location is NULL until manually assigned via util_set_competition_location.sql
-- pool_course defaults to SC — update via util_update_pool_course.sql when needed
-- -----------------------------------------------------------------------------
CREATE TABLE competitions (
    id             SERIAL       PRIMARY KEY,
    competition_id VARCHAR(50)  UNIQUE NOT NULL,
    loglig_id      VARCHAR(50),
    name           TEXT         NOT NULL,
    location       TEXT,                        -- NULL until manually set
    start_date     DATE,
    end_date       DATE,
    sport_type     TEXT,
    pool_course    VARCHAR(2)   NOT NULL DEFAULT 'SC' CHECK (pool_course IN ('SC', 'LC')),
    scraped_at     TIMESTAMPTZ  DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- clubs
-- -----------------------------------------------------------------------------
CREATE TABLE clubs (
    id          SERIAL  PRIMARY KEY,
    loglig_id   INT     UNIQUE,
    name        TEXT    NOT NULL UNIQUE
);

-- -----------------------------------------------------------------------------
-- swimmers
-- Primary natural key: loglig_id (stable external id from /Players/Details/{id})
-- Fallback natural key: (full_name, birth_year) for swimmers without a profile link
-- club_id = home club at registration time; club at race time is on results
-- -----------------------------------------------------------------------------
CREATE TABLE swimmers (
    id          SERIAL       PRIMARY KEY,
    loglig_id   VARCHAR(50)  UNIQUE,
    full_name   TEXT         NOT NULL,
    birth_year  INT,
    club_id     INT          REFERENCES clubs(id),
    gender      VARCHAR(5),
    UNIQUE (full_name, birth_year)
);

-- -----------------------------------------------------------------------------
-- events
-- One row per race within a competition. Maps to Race in models.py.
-- Age group is NOT stored — derived at query time from swimmer birth_year + race_date
-- -----------------------------------------------------------------------------
CREATE TABLE events (
    id              SERIAL   PRIMARY KEY,
    competition_id  INT      NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    loglig_event_id VARCHAR(50),
    event_num       INT,
    name            TEXT     NOT NULL,
    distance_m      INT,
    stroke          VARCHAR(30),
    gender          VARCHAR(10),
    category        TEXT,
    is_relay        BOOLEAN  NOT NULL DEFAULT FALSE,
    race_date       DATE,
    start_time      TEXT,
    pool_course     VARCHAR(2) NOT NULL DEFAULT 'SC' CHECK (pool_course IN ('SC', 'LC')),
    UNIQUE (competition_id, loglig_event_id)
);

-- -----------------------------------------------------------------------------
-- heats
-- -----------------------------------------------------------------------------
CREATE TABLE heats (
    id       SERIAL  PRIMARY KEY,
    event_id INT     NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    heat_num INT     NOT NULL,
    UNIQUE (event_id, heat_num)
);

-- -----------------------------------------------------------------------------
-- results
-- One row per swimmer per heat. Core individual fact table.
-- club_id = club at time of race (not necessarily swimmer's current club)
-- time_ms = milliseconds (e.g. "25.43" → 25430). NULL if DSQ or DNS.
-- splits  = JSONB: {"1": "25.43", "2": "51.22", ...} (ascending cumulative)
-- -----------------------------------------------------------------------------
CREATE TABLE results (
    id            SERIAL   PRIMARY KEY,
    heat_id       INT      NOT NULL REFERENCES heats(id) ON DELETE CASCADE,
    swimmer_id    INT      NOT NULL REFERENCES swimmers(id),
    club_id       INT      REFERENCES clubs(id),
    lane          INT,
    time_ms       INT,
    dsq           BOOLEAN  NOT NULL DEFAULT FALSE,
    dns           BOOLEAN  NOT NULL DEFAULT FALSE,
    place         INT,
    points        INT,
    team_points   INT,
    reaction_time VARCHAR(20),
    splits        JSONB,
    scraped_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (heat_id, swimmer_id)
);

-- -----------------------------------------------------------------------------
-- relay_results
-- One row per relay team per heat.
-- swimmer_ids = ordered INT array: leg 0..3, each a FK to swimmers.id
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- schema_migrations
-- -----------------------------------------------------------------------------
CREATE TABLE schema_migrations (
    version     VARCHAR(50)  PRIMARY KEY,
    applied_at  TIMESTAMPTZ  DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- indexes
-- -----------------------------------------------------------------------------
CREATE INDEX idx_results_swimmer            ON results(swimmer_id);
CREATE INDEX idx_results_heat               ON results(heat_id);
CREATE INDEX idx_results_swimmer_time_valid ON results(swimmer_id, time_ms)
    WHERE time_ms IS NOT NULL AND dsq = FALSE AND dns = FALSE;
CREATE INDEX idx_competitions_date          ON competitions(start_date);
CREATE INDEX idx_events_competition         ON events(competition_id);
CREATE INDEX idx_events_stroke_distance     ON events(stroke, distance_m);
CREATE INDEX idx_heats_event                ON heats(event_id);
CREATE INDEX idx_relay_results_heat         ON relay_results(heat_id);
CREATE INDEX idx_relay_results_club         ON relay_results(club_id);