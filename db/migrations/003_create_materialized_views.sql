-- 003_create_materialized_views.sql
-- Materialized views for dashboard performance.
-- Refresh these after each ETL run or on a schedule.

BEGIN;

-- Daily cost aggregation by service
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_cost_by_service AS
SELECT
    date_trunc('day', chargeperiodstart)::date   AS cost_date,
    servicename,
    servicecategory,
    SUM(billedcost)                               AS total_billed_cost,
    SUM(effectivecost)                            AS total_effective_cost,
    SUM(listcost)                                 AS total_list_cost,
    COUNT(*)                                      AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_service
    ON mv_daily_cost_by_service (cost_date, servicename, servicecategory);

-- Daily cost aggregation by compartment
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_cost_by_compartment AS
SELECT
    date_trunc('day', chargeperiodstart)::date   AS cost_date,
    oci_compartmentname                           AS compartment_name,
    oci_compartmentid                             AS compartment_id,
    SUM(billedcost)                               AS total_billed_cost,
    SUM(effectivecost)                            AS total_effective_cost,
    COUNT(*)                                      AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_compartment
    ON mv_daily_cost_by_compartment (cost_date, compartment_name, compartment_id);

-- Monthly cost summary with month-over-month change
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_cost_summary AS
WITH monthly AS (
    SELECT
        date_trunc('month', billingperiodstart)::date AS cost_month,
        SUM(billedcost)                                AS total_billed_cost,
        SUM(effectivecost)                             AS total_effective_cost,
        SUM(listcost)                                  AS total_list_cost,
        COUNT(*)                                       AS line_item_count
    FROM oci_finops_reports
    GROUP BY 1
)
SELECT
    m.cost_month,
    m.total_billed_cost,
    m.total_effective_cost,
    m.total_list_cost,
    m.line_item_count,
    LAG(m.total_billed_cost) OVER (ORDER BY m.cost_month) AS prev_month_billed_cost,
    CASE
        WHEN LAG(m.total_billed_cost) OVER (ORDER BY m.cost_month) > 0
        THEN ROUND(
            ((m.total_billed_cost - LAG(m.total_billed_cost) OVER (ORDER BY m.cost_month))
             / LAG(m.total_billed_cost) OVER (ORDER BY m.cost_month)) * 100, 2
        )
        ELSE NULL
    END AS mom_change_pct
FROM monthly m
ORDER BY m.cost_month DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_monthly_summary
    ON mv_monthly_cost_summary (cost_month);

-- Cost by region
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cost_by_region AS
SELECT
    date_trunc('day', chargeperiodstart)::date   AS cost_date,
    region,
    SUM(billedcost)                               AS total_billed_cost,
    SUM(effectivecost)                            AS total_effective_cost,
    COUNT(*)                                      AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2
ORDER BY 1 DESC, 4 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_cost_region
    ON mv_cost_by_region (cost_date, region);

-- Helper function to refresh all materialized views (call after ETL)
CREATE OR REPLACE FUNCTION refresh_finops_views()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_service;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_compartment;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_cost_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cost_by_region;
END;
$$;

COMMIT;
