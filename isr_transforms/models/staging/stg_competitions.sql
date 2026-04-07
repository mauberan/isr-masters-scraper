SELECT
    id              AS competition_id,
    competition_id  AS isr_id,
    loglig_id,
    name            AS competition_name,
    location,
    start_date,
    end_date,
    sport_type,
    pool_course,
    scraped_at
FROM {{ source('isr', 'competitions') }}