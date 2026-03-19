-- migrations/007_relay_results_unique_constraint.sql
--
-- NOTE: The UNIQUE (heat_id, club_id, lane) constraint is already included
-- in migration 006 and schema.sql. This file is a no-op marker kept for
-- historical accuracy (it was drafted separately before 006 was finalized).

INSERT INTO schema_migrations (version)
VALUES ('007_relay_results_unique_constraint')
ON CONFLICT (version) DO NOTHING;
