-- db/queries/personal_bests.sql
--
-- Personal best time per swimmer per event (stroke + distance).
-- Only counts valid swims — excludes DSQ, DNS, and null times.
--
-- Age group is derived from birth_year and competition year.

WITH valid_results AS (
    SELECT
        r.id,
        r.swimmer_id,
        r.time_ms,
        r.club,
        e.name        AS event_name,
        e.stroke,
        e.distance_m,
        e.gender,
        e.pool_course,
        c.start_date,
        EXTRACT(YEAR FROM c.start_date) - s.birth_year AS age_at_competition
    FROM results r
    JOIN heats h        ON h.id = r.heat_id
    JOIN events e       ON e.id = h.event_id
    JOIN competitions c ON c.id = e.competition_id
    JOIN swimmers s     ON s.id = r.swimmer_id
    WHERE r.dsq    = FALSE
      AND r.dns    = FALSE
      AND r.time_ms IS NOT NULL
),
personal_bests AS (
    SELECT
        swimmer_id,
        stroke,
        distance_m,
        gender,
        MIN(time_ms) AS pb_ms
    FROM valid_results
    GROUP BY swimmer_id, stroke, distance_m, gender, pool_course
)
SELECT
    s.full_name,
    s.birth_year,
    pb.gender,
    pb.pool_course,
    pb.distance_m,
    pb.stroke,
    -- convert ms back to readable time
    CASE
        WHEN pb.pb_ms >= 60000
        THEN CONCAT(pb.pb_ms / 60000, ':', LPAD(((pb.pb_ms % 60000) / 1000.0)::TEXT, 5, '0'))
        ELSE ROUND(pb.pb_ms / 1000.0, 2)::TEXT
    END                         AS pb_time,
    pb.pb_ms                    AS pb_ms
FROM personal_bests pb
JOIN swimmers s ON s.id = pb.swimmer_id
ORDER BY s.full_name, pb.distance_m, pb.stroke;
