-- 002_create_indexes.sql
-- Performance indexes for common query patterns.

BEGIN;

-- Time-range queries (most dashboards filter by date)
CREATE INDEX IF NOT EXISTS idx_reports_billingperiodstart
    ON oci_finops_reports (billingperiodstart);

-- Service-level analysis
CREATE INDEX IF NOT EXISTS idx_reports_servicename
    ON oci_finops_reports (servicename);

-- Regional cost breakdown
CREATE INDEX IF NOT EXISTS idx_reports_region
    ON oci_finops_reports (region);

-- Compartment analysis
CREATE INDEX IF NOT EXISTS idx_reports_compartmentname
    ON oci_finops_reports (oci_compartmentname);

-- Charge category filtering (Usage, Purchase, Tax, etc.)
CREATE INDEX IF NOT EXISTS idx_reports_chargecategory
    ON oci_finops_reports (chargecategory);

-- Sub-account analysis
CREATE INDEX IF NOT EXISTS idx_reports_subaccountname
    ON oci_finops_reports (subaccountname);

-- JSONB GIN index for tag-based queries
CREATE INDEX IF NOT EXISTS idx_reports_tags
    ON oci_finops_reports USING GIN (tags);

-- Composite index for the most common dashboard query pattern
CREATE INDEX IF NOT EXISTS idx_reports_period_service
    ON oci_finops_reports (billingperiodstart, servicename);

-- Watermark lookup by status (for monitoring failed loads)
CREATE INDEX IF NOT EXISTS idx_watermark_status
    ON etl_watermark (status) WHERE status != 'success';

COMMIT;
