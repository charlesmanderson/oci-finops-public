-- 008_retired_recategorization.sql
-- (Retired) This migration previously re-categorized a compartment mapping.
-- Compartment → customer/team mappings are now deploy-time reference data
-- (db/seed/reference_data.local.sql), applied after migrations with their final
-- categorization, so this per-compartment fixup is no longer needed here.
--
-- Kept as a no-op to preserve the migration sequence for databases that have
-- not yet applied it.

BEGIN;
COMMIT;
