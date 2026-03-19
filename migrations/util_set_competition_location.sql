-- migrations/util_set_competition_location.sql
--
-- Utility: manually assign a location to a competition.
--
-- The scraper does not collect location — it is not available on the ISR site.
-- Use this script to set it manually after scraping.
--
-- Usage:
--   psql postgresql://isr:isr@localhost:5432/isr_masters \
--     -v competition_id="'42'" \
--     -v location="'Wingate Institute, Netanya'" \
--     -f migrations/util_set_competition_location.sql
--
-- To see all competitions and their current locations:
--   psql postgresql://isr:isr@localhost:5432/isr_masters \
--     -c "SELECT competition_id, name, start_date, location FROM competitions ORDER BY start_date DESC;"

DO $$
DECLARE
    v_competition_id TEXT := :'competition_id';
    v_location       TEXT := :'location';
    v_internal_id    INT;
    v_name           TEXT;
BEGIN
    SELECT id, name INTO v_internal_id, v_name
    FROM competitions
    WHERE competition_id = v_competition_id;

    IF v_internal_id IS NULL THEN
        RAISE EXCEPTION 'Competition with competition_id "%" not found.', v_competition_id;
    END IF;

    UPDATE competitions
    SET location = v_location
    WHERE id = v_internal_id;

    RAISE NOTICE 'Updated competition "%" (id=%) → location = "%".',
        v_name, v_internal_id, v_location;
END;
$$;
