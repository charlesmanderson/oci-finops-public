-- reference_data.example.sql
--
-- Template for deploy-time reference data (real tenancy OCIDs + customer names).
-- These rows are intentionally NOT committed to the repo. To deploy:
--
--   1. cp db/seed/reference_data.example.sql db/seed/reference_data.local.sql
--   2. fill in your real tenancies, compartment→group mappings, and customers
--   3. python -m etl.pipeline --init-db --seed   (seed runs AFTER migrations)
--
-- db/seed/*.local.sql is gitignored. Every statement is an idempotent UPSERT,
-- so re-running is safe and re-seeding reflects edits. Order matters because of
-- foreign keys: tenancies -> tenancy_customers, and customer_groups is
-- referenced by the group dashboards.

BEGIN;

-- 1. Tenancies (one row per OCI tenancy you ingest) --------------------------
--    config_profile must match a profile in ~/.oci/config for that tenancy.
INSERT INTO tenancies (alias, tenancy_ocid, home_region, namespace, config_profile, display_name) VALUES
    ('primary', 'ocid1.tenancy.oc1..OWNER_TENANCY_OCID',    'us-ashburn-1', 'bling', 'DEFAULT',    'Primary Tenancy'),
    ('customer01',   'ocid1.tenancy.oc1..CUSTOMER_TENANCY_OCID', 'us-phoenix-1', 'bling', 'CUSTOMER01', 'Customer 01')
ON CONFLICT (alias) DO UPDATE
    SET tenancy_ocid   = EXCLUDED.tenancy_ocid,
        home_region    = EXCLUDED.home_region,
        namespace      = EXCLUDED.namespace,
        config_profile = EXCLUDED.config_profile,
        display_name   = EXCLUDED.display_name;

-- 2. Compartment -> customer/team mappings (formerly migrations 006 + 007) ---
--    group_name 'Internal' with a sub_team for your own teams; a customer name
--    with sub_team NULL for external customers.
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('EXAMPLE_EXTERNAL_CMP', 'Example Customer', NULL, 'Example Customer'),
    ('EXAMPLE_INTERNAL_CMP', 'Internal',         'AI', 'AI - Example')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- 3. Whole-tenancy customers (external customers billed at the tenancy level) -
INSERT INTO tenancy_customers (tenancy_alias, group_name, display_name, sub_team) VALUES
    ('customer01', 'Customer 01', 'Customer 01', NULL)
ON CONFLICT (tenancy_alias) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        display_name = EXCLUDED.display_name,
        sub_team     = EXCLUDED.sub_team;

COMMIT;
