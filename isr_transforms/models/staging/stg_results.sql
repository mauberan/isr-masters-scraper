-- models/staging/stg_results.sql
SELECT
    id                                          AS result_id,
    heat_id,
    swimmer_id,
    club_id,
    lane,
    time_ms,
    time_ms / 1000.0                            AS time_seconds,
    CASE
        WHEN time_ms >= 60000
        THEN LPAD((time_ms / 60000)::TEXT, 1, '0')
             || ':'
             || LPAD(((time_ms % 60000) / 1000)::TEXT, 2, '0')
             || '.'
             || LPAD((time_ms % 1000)::TEXT, 3, '0')
        ELSE LPAD((time_ms / 1000)::TEXT, 2, '0')
             || '.'
             || LPAD((time_ms % 1000)::TEXT, 3, '0')
    END                                         AS time_formatted,
    place,
    points,
    team_points,
    reaction_time,
    splits,
    scraped_at
FROM {{ source('isr', 'results') }}
WHERE dsq = FALSE
  AND dns = FALSE
  AND time_ms IS NOT NULL