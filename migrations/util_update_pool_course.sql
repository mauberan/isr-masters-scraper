-- migrations/util_update_pool_course.sql
--
-- Utility script: manually update pool_course for an entire competition
-- and all its child events.
--
-- Use this when a competition was imported as SC but is actually LC,
-- or when you want to correct historical data.
--
-- This is NOT a numbered migration — it is a utility script meant to be
-- run manually with parameters. It is safe to run multiple times.
--
-- Usage:
--   psql postgresql://isr:isr@localhost:5432/isr_masters \
--     -v competition_id="'42'" \
--     -v course="'LC'" \
--     -f migrations/util_update_pool_course.sql
--
-- Parameters:
--   :competition_id  — the ISR competition_id string (e.g. '42')
--   :course          — 'SC' or 'LC'

DO $$
DECLARE
    v_competition_id TEXT    := :'competition_id';
    v_course         VARCHAR := :'course';
    v_internal_id    INT;
    v_event_count    INT;
BEGIN
    -- Validate course value
    IF v_course NOT IN ('SC', 'LC') THEN
        RAISE EXCEPTION 'Invalid course value "%". Must be SC or LC.', v_course;
    END IF;

    -- Resolve internal id from ISR competition_id
    SELECT id INTO v_internal_id
    FROM competitions
    WHERE competition_id = v_competition_id;

    IF v_internal_id IS NULL THEN
        RAISE EXCEPTION 'Competition with competition_id "%" not found.', v_competition_id;
    END IF;

    -- Update competition
    UPDATE competitions
    SET pool_course = v_course
    WHERE id = v_internal_id;

    -- Update all child events
    UPDATE events
    SET pool_course = v_course
    WHERE competition_id = v_internal_id;

    GET DIAGNOSTICS v_event_count = ROW_COUNT;

    RAISE NOTICE 'Updated competition "%" (id=%) and % event(s) to pool_course = %.',
        v_competition_id, v_internal_id, v_event_count, v_course;
END;
$$;