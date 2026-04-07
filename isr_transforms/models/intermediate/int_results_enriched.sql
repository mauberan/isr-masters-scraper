SELECT
    r.result_id,
    r.heat_id,
    r.time_ms,
    r.time_seconds,
    r.time_formatted,
    r.place,
    r.points,
    r.team_points,
    r.lane,
    r.reaction_time,

    s.swimmer_id,
    s.full_name      AS swimmer_name,
    s.birth_year,
    s.gender,

    c.club_name,

    e.event_id,
    e.event_name,
    e.distance_m, 
    e.stroke,
    e.pool_course,
    e.race_date,

    comp.competition_id,
    comp.competition_name,
    comp.start_date  AS competition_date,

    EXTRACT(YEAR FROM e.race_date) - s.birth_year
                     AS age_at_race,
    CONCAT(
        (FLOOR((EXTRACT(YEAR FROM e.race_date) - s.birth_year) / 5) * 5)::INT,
        '-',
        (FLOOR((EXTRACT(YEAR FROM e.race_date) - s.birth_year) / 5) * 5 + 4)::INT
    )                AS age_group

FROM {{ ref('stg_results') }}          r
JOIN {{ source('isr', 'heats') }}      h    ON h.id          = r.heat_id
JOIN {{ ref('stg_events') }}           e    ON e.event_id    = h.event_id
LEFT JOIN {{ ref('stg_clubs') }}       c    ON c.club_id     = r.club_id
JOIN {{ ref('stg_swimmers') }}         s    ON s.swimmer_id  = r.swimmer_id
JOIN {{ ref('stg_competitions') }}     comp ON comp.competition_id = e.competition_id
WHERE s.birth_year IS NOT NULL
  AND e.race_date  IS NOT NULL