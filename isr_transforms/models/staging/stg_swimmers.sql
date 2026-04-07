SELECT
    id              AS swimmer_id,
    loglig_id,
    full_name,
    birth_year,
    club_id,
    gender
FROM {{ source('isr', 'swimmers') }}
WHERE full_name IS NOT NULL
  AND full_name != ''
  