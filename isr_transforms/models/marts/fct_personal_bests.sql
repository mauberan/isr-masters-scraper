SELECT
    swimmer_id,
    swimmer_name,
    birth_year,
    gender,
    distance_m,
    stroke,
    pool_course,
    MIN(time_ms)                        AS pb_ms,
    MIN(time_seconds)                   AS pb_seconds,
    MIN(time_formatted)                 AS pb_formatted,
    (ARRAY_AGG(competition_name ORDER BY time_ms ASC))[1]
                                        AS pb_competition,
    (ARRAY_AGG(competition_date ORDER BY time_ms ASC))[1]
                                        AS pb_date,
    (ARRAY_AGG(age_group ORDER BY time_ms ASC))[1]
                                        AS age_group_at_pb
FROM {{ ref('int_results_enriched') }}
GROUP BY swimmer_id, swimmer_name, birth_year, gender, distance_m, stroke, pool_course
ORDER BY swimmer_name, distance_m, stroke