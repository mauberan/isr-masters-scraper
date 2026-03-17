-- =============================================================================
-- ISR Masters Scraper — Initial Schema
-- Module 2: Schema Design
-- =============================================================================

-- -----------------------------------------------------------------------------
-- competitions
-- One row per swim meet scraped from the ISR site.
-- -----------------------------------------------------------------------------
CREATE TABLE competitions (
    id             SERIAL PRIMARY KEY,
    competition_id VARCHAR(50)  UNIQUE NOT NULL,  -- ISR's own ID (from URL/DOM)
    name           TEXT         NOT NULL,
    location       TEXT,
    start_date     DATE         NOT NULL,
    end_date       DATE,
    scraped_at     TIMESTAMPTZ  DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- swimmers
-- One row per unique person. Identity: (full_name, birth_year).
-- Club is NOT stored here — it is stored on results, because swimmers change clubs.
-- -----------------------------------------------------------------------------
CREATE TABLE swimmers (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT  NOT NULL,
    birth_year  INT   NOT NULL,
    UNIQUE (full_name, birth_year)
);

-- -----------------------------------------------------------------------------
-- events
-- A specific race within a competition: e.g. "50m Freestyle Men".
-- Age group is NOT stored — it is derived at query time from swimmer birth_year
-- and competition start_date.
-- -----------------------------------------------------------------------------
CREATE TABLE events (
    id             SERIAL  PRIMARY KEY,
    competition_id INT     NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,   -- full name as scraped, e.g. "50m Freestyle"
    distance_m     INT,               -- 50, 100, 200, 400, 800, 1500
    stroke         VARCHAR(30),       -- freestyle, backstroke, breaststroke, butterfly, medley
    gender         VARCHAR(10)        -- M / F
);

-- -----------------------------------------------------------------------------
-- heats
-- A sub-group of swimmers within an event, split by seed time.
-- -----------------------------------------------------------------------------
CREATE TABLE heats (
    id       SERIAL  PRIMARY KEY,
    event_id INT     NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    heat_num INT     NOT NULL
);

-- -----------------------------------------------------------------------------
-- results
-- One row per swimmer per heat. The core fact table.
-- club is stored here (not on swimmers) to capture club at time of race.
-- time_ms stores milliseconds (e.g. "25.43" → 25430) for numeric operations.
-- -----------------------------------------------------------------------------
CREATE TABLE results (
    id          SERIAL  PRIMARY KEY,
    heat_id     INT     NOT NULL REFERENCES heats(id) ON DELETE CASCADE,
    swimmer_id  INT     NOT NULL REFERENCES swimmers(id),
    club        TEXT,                          -- club at time of this race
    lane        INT,
    time_ms     INT,                           -- NULL if DSQ or DNS
    dsq         BOOLEAN NOT NULL DEFAULT FALSE,
    dns         BOOLEAN NOT NULL DEFAULT FALSE,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    -- a swimmer can only appear once per heat
    UNIQUE (heat_id, swimmer_id)
);

-- -----------------------------------------------------------------------------
-- schema_migrations
-- Tracks which migration files have been applied.
-- Used by the manual migration runner (see migrations/).
-- -----------------------------------------------------------------------------
CREATE TABLE schema_migrations (
    version     VARCHAR(50)  PRIMARY KEY,
    applied_at  TIMESTAMPTZ  DEFAULT now()
);