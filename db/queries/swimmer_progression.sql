-- db/queries/swimmer_progression.sql
--
-- Time progression for a specific swimmer in a specific event over time.
-- Shows improvement (or regression) across competitions chronologically.
--
-- Replace :swimmer_name, :stroke, :distance_m with actual values,
-- or use via the Python query helper in db/queries.py.
--
-- Example:
--   \set swimmer_name 'Lior Cohen'
--   \set stroke 'freestyle'
--   \set distance_m 50
--   \i db/queries/swimmer_progression.sql

SELECT
    c.start_date                                        AS date,
    c.name                                              AS competition,
    r.club                                              AS club_at_race,
    EXTRACT(YEAR FROM c.start_date) - s.birth_year      AS age,
    CASE
        WHEN r.dsq THEN 'DSQ'
        WHEN r.dns THEN 'DNS'
        WHEN r.time_ms >= 60000
        THEN CONCAT(r.time_ms / 60000, ':', LPAD(((r.time_ms % 60000) / 1000.0)::TEXT, 5, '0'))
        ELSE ROUND(r.time_ms / 1000.0, 2)::TEXT
    END                                                 AS time,
    r.time_ms,
    -- delta from previous race (negative = improvement)
    r.time_ms - LAG(r.time_ms) OVER (ORDER BY c.start_date) AS delta_ms
FROM results r
JOIN heats h        ON h.id  = r.heat_id
JOIN events e       ON e.id  = h.event_id
JOIN competitions c ON c.id  = e.competition_id
JOIN swimmers s     ON s.id  = r.swimmer_id
WHERE s.full_name   = :swimmer_name
  AND e.stroke      = :stroke
  AND e.distance_m  = :distance_m
  AND r.dsq = FALSE
  AND r.dns = FALSE
ORDER BY c.start_date;
