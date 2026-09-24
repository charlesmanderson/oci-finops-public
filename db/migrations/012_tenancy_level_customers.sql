-- 012_tenancy_level_customers.sql
-- Adds the `tenancy_customers` table for customers reported at the
-- whole-tenancy level (rather than per-compartment, which is the model in
-- `customer_groups`). Used by the "Customer Monthly Spend" dashboard.
-- Customer rows are deploy-time reference data, applied after migrations from
-- db/seed/reference_data.local.sql — not committed here.
--
-- Idempotent: re-runs are safe.

BEGIN;

CREATE TABLE IF NOT EXISTS tenancy_customers (
    tenancy_alias   TEXT        PRIMARY KEY REFERENCES tenancies(alias),
    group_name      TEXT        NOT NULL,
    display_name    TEXT        NOT NULL,
    sub_team        TEXT,   -- NULL => external customer (matches the
                            -- "WHERE sub_team IS NULL" pattern used by the
                            -- customer-list dropdown query)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
