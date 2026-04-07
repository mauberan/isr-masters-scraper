SELECT
    club_name,
    COUNT(DISTINCT swimmer_id)          AS total_swimmers,
    COUNT(DISTINCT competition_id)      AS competitions_entered,
    COUNT(result_id)                    AS total_results,
    SUM(points)                         AS total_points,
    SUM(team_points)                    AS total_team_points,
    AVG(time_seconds)                   AS avg_time_seconds,
    MIN(time_seconds)                   AS best_time_seconds
FROM {{ ref('int_results_enriched') }}
WHERE club_name IS NOT NULL
GROUP BY club_name
ORDER BY total_points DESC NULLS LAST