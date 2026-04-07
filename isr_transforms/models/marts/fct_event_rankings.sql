WITH best_per_swimmer AS (
    SELECT DISTINCT ON (swimmer_id, distance_m, stroke, pool_course, age_group)
        swimmer_id,
        swimmer_name,
        birth_year,
        gender,
        club_name,
        distance_m,
        stroke,
        pool_course,
        age_group,
        time_ms,
        time_formatted,
        competition_name,
        competition_date
    FROM {{ ref('int_results_enriched') }}
    ORDER BY swimmer_id, distance_m, stroke, pool_course, age_group, time_ms ASC
)
SELECT
    *,
    RANK() OVER (
        PARTITION BY distance_m, stroke, pool_course, age_group, gender
        ORDER BY time_ms ASC
    ) AS rank_in_age_group
FROM best_per_swimmer
ORDER BY distance_m, stroke, pool_course, age_group, gender, rank_in_age_group