-- 007_move_compartments_to_ai.sql
-- (Retired) This migration previously seeded and re-categorized compartment →
-- customer/team mappings. That reference data now lives in the deploy-time seed
-- (db/seed/reference_data.local.sql), applied after migrations, so the final
-- mapping state is set there rather than accreted across migrations.
--
-- Kept as a no-op to preserve the migration sequence for databases that have
-- not yet applied it.

BEGIN;
COMMIT;
