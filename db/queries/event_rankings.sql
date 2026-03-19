-- db/queries/event_rankings.sql
--
-- Top results for a given event across all competitions,
-- grouped by age bracket (derived from birth_year).
--
-- One row per swimmer — their best time only (not every swim).
-- Ranked within each age group.

WITH valid_results AS (
    SELECT
        r.swimmer_id,
        r.club,
        r.time_ms,
        e.stroke,
        e.distance_m,
        e.gender,
        c.name                                              AS competition,
        c.start_date,
        EXTRACT(YEAR FROM c.start_date) - s.birth_year      AS age
    FROM results r
    JOIN heats h        ON h.id = r.heat_id
    JOIN events e       ON e.id = h.event_id
    JOIN competitions c ON c.id = e.competition_id
    JOIN swimmers s     ON s.id = r.swimmer_id
    WHERE e.stroke     = :stroke
      AND e.distance_m = :distance_m
      AND e.gender     = :gender
      AND e.pool_course = :pool_course
      AND r.dsq = FALSE
      AND r.dns = FALSE
      AND r.time_ms IS NOT NULL
),
best_per_swimmer AS (
    -- one row per swimmer: their fastest time for this event
    SELECT DISTINCT ON (swimmer_id)
        swimmer_id,
        club,
        time_ms,
        competition,
        start_date,
        age
    FROM valid_results
    ORDER BY swimmer_id, time_ms ASC
),
age_groups AS (
    SELECT
        *,
        -- FINA Masters age groups: 25-29, 30-34, 35-39 ... 100-104
        CONCAT(
            (FLOOR(age / 5) * 5)::INT, '-',
            (FLOOR(age / 5) * 5 + 4)::INT
        ) AS age_group
    FROM best_per_swimmer
)
SELECT
    age_group,
    RANK() OVER (PARTITION BY age_group ORDER BY time_ms)   AS rank,
    s.full_name,
    s.birth_year,
    a.club,
    CASE
        WHEN a.time_ms >= 60000
        THEN CONCAT(a.time_ms / 60000, ':', LPAD(((a.time_ms % 60000) / 1000.0)::TEXT, 5, '0'))
        ELSE ROUND(a.time_ms / 1000.0, 2)::TEXT
    END                                                     AS time,
    a.competition,
    a.start_date
FROM age_groups a
JOIN swimmers s ON s.id = a.swimmer_id
ORDER BY age_group, rank;
