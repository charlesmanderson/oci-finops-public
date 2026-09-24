-- 009_multi_tenancy.sql
-- Adds a tenancies lookup table and a tenancy_alias discriminator column to
-- the fact table, watermark, and anomalies. Backfills existing rows to
-- 'primary' via a column DEFAULT (metadata-only on PG 11+ for literal
-- defaults, so this is instant even on large tables).
--
-- Idempotent: re-runs are safe.

BEGIN;

-- 1. Tenancies lookup table -------------------------------------------------

CREATE TABLE IF NOT EXISTS tenancies (
    alias           TEXT        PRIMARY KEY,
    tenancy_ocid    TEXT        NOT NULL UNIQUE,
    home_region     TEXT        NOT NULL,
    namespace       TEXT        NOT NULL DEFAULT 'bling',
    config_profile  TEXT        NOT NULL,
    display_name    TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bootstrap the owner tenancy only. The FK added below backfills every existing
-- row to 'primary', so that alias MUST exist before the FK is validated.
-- Real tenancy_ocid values and all customer tenancies are deploy-time reference
-- data, applied after migrations from db/seed/reference_data.local.sql. This
-- placeholder row is overwritten by that seed's ON CONFLICT DO UPDATE.
INSERT INTO tenancies (alias, tenancy_ocid, home_region, namespace, config_profile, display_name) VALUES
    ('primary', 'ocid1.tenancy.oc1..PLACEHOLDER', 'us-ashburn-1', 'bling', 'DEFAULT', 'Primary Tenancy')
ON CONFLICT (alias) DO NOTHING;

-- 2. oci_finops_reports: add tenancy_alias ----------------------------------
-- A NOT NULL column with a literal DEFAULT is metadata-only in PG 11+,
-- so adding it to a large partitioned table is instant.

ALTER TABLE oci_finops_reports
    ADD COLUMN IF NOT EXISTS tenancy_alias TEXT NOT NULL DEFAULT 'primary';

-- Drop the default so future INSERTs must specify it explicitly.
ALTER TABLE oci_finops_reports ALTER COLUMN tenancy_alias DROP DEFAULT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_oci_finops_reports_tenancy'
    ) THEN
        -- PG 16 does not support NOT VALID FK on partitioned tables, so this
        -- validates the full table during creation. With every existing row
        -- defaulted to 'primary' (which exists in tenancies), the scan
        -- is straight-line and completes in a couple minutes.
        ALTER TABLE oci_finops_reports
            ADD CONSTRAINT fk_oci_finops_reports_tenancy
            FOREIGN KEY (tenancy_alias) REFERENCES tenancies(alias);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_oci_finops_reports_tenancy_period
    ON oci_finops_reports (tenancy_alias, billingperiodstart);

-- 3. etl_watermark: add tenancy_alias + recompose PK ------------------------

ALTER TABLE etl_watermark
    ADD COLUMN IF NOT EXISTS tenancy_alias TEXT NOT NULL DEFAULT 'primary';
ALTER TABLE etl_watermark ALTER COLUMN tenancy_alias DROP DEFAULT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_watermark_pkey'
          AND conrelid = 'etl_watermark'::regclass
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = 'etl_watermark_pkey'
          AND array_length(i.indkey::int[], 1) = 2
    ) THEN
        ALTER TABLE etl_watermark DROP CONSTRAINT etl_watermark_pkey;
        ALTER TABLE etl_watermark ADD PRIMARY KEY (tenancy_alias, file_path);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_etl_watermark_tenancy'
    ) THEN
        ALTER TABLE etl_watermark
            ADD CONSTRAINT fk_etl_watermark_tenancy
            FOREIGN KEY (tenancy_alias) REFERENCES tenancies(alias);
    END IF;
END $$;

-- 4. cost_anomalies: add tenancy_alias --------------------------------------

ALTER TABLE cost_anomalies
    ADD COLUMN IF NOT EXISTS tenancy_alias TEXT NOT NULL DEFAULT 'primary';
ALTER TABLE cost_anomalies ALTER COLUMN tenancy_alias DROP DEFAULT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_cost_anomalies_tenancy'
    ) THEN
        ALTER TABLE cost_anomalies
            ADD CONSTRAINT fk_cost_anomalies_tenancy
            FOREIGN KEY (tenancy_alias) REFERENCES tenancies(alias);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_anomalies_tenancy_date
    ON cost_anomalies (tenancy_alias, detection_date DESC);

COMMIT;
