SELECT
    id          AS club_id,
    name        AS club_name
FROM {{ source('isr', 'clubs') }}
WHERE name IS NOT NULL