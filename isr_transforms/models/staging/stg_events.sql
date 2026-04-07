SELECT
    id              AS event_id,
    competition_id,
    loglig_event_id,
    event_num,
    name            AS event_name,
    distance_m,
    LOWER(stroke)   AS stroke,
    UPPER(gender)   AS gender,
    category,
    is_relay,
    race_date,
    pool_course
FROM {{ source('isr', 'events') }}
WHERE is_relay = FALSE