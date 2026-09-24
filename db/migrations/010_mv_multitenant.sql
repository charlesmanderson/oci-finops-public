-- 010_mv_multitenant.sql
-- Recreate the 5 materialized views with tenancy_alias as a leading column,
-- so dashboards can filter by tenancy without mixing data across tenancies.
-- mv_daily_cost_by_group's LEFT JOIN fallback uses 'Unmapped' for compartments
-- not present in customer_groups (instead of the previous 'Internal/Ops'
-- default which would mislabel compartments from new tenancies).
--
-- DROP MATERIALIZED VIEW IF EXISTS is used because adding a column requires
-- recreating the view; CREATE MATERIALIZED VIEW IF NOT EXISTS would be a
-- no-op against the old definition.

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS mv_daily_cost_by_service     CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_daily_cost_by_compartment CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_monthly_cost_summary      CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_cost_by_region            CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_daily_cost_by_group       CASCADE;

-- Daily cost by service (per-tenancy) --------------------------------------

CREATE MATERIALIZED VIEW mv_daily_cost_by_service AS
SELECT
    tenancy_alias,
    date_trunc('day', chargeperiodstart)::date    AS cost_date,
    servicename,
    servicecategory,
    SUM(billedcost)                                AS total_billed_cost,
    SUM(effectivecost)                             AS total_effective_cost,
    SUM(listcost)                                  AS total_list_cost,
    COUNT(*)                                       AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2, 3, 4
ORDER BY 2 DESC, 5 DESC;

CREATE UNIQUE INDEX idx_mv_daily_service
    ON mv_daily_cost_by_service (tenancy_alias, cost_date, servicename, servicecategory);

-- Daily cost by compartment (per-tenancy) ----------------------------------

CREATE MATERIALIZED VIEW mv_daily_cost_by_compartment AS
SELECT
    tenancy_alias,
    date_trunc('day', chargeperiodstart)::date    AS cost_date,
    oci_compartmentname                            AS compartment_name,
    oci_compartmentid                              AS compartment_id,
    SUM(billedcost)                                AS total_billed_cost,
    SUM(effectivecost)                             AS total_effective_cost,
    COUNT(*)                                       AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2, 3, 4
ORDER BY 2 DESC, 5 DESC;

CREATE UNIQUE INDEX idx_mv_daily_compartment
    ON mv_daily_cost_by_compartment (tenancy_alias, cost_date, compartment_name, compartment_id);

-- Monthly cost summary with month-over-month change (per-tenancy) ----------

CREATE MATERIALIZED VIEW mv_monthly_cost_summary AS
WITH monthly AS (
    SELECT
        tenancy_alias,
        date_trunc('month', billingperiodstart)::date AS cost_month,
        SUM(billedcost)                                AS total_billed_cost,
        SUM(effectivecost)                             AS total_effective_cost,
        SUM(listcost)                                  AS total_list_cost,
        COUNT(*)                                       AS line_item_count
    FROM oci_finops_reports
    GROUP BY 1, 2
)
SELECT
    m.tenancy_alias,
    m.cost_month,
    m.total_billed_cost,
    m.total_effective_cost,
    m.total_list_cost,
    m.line_item_count,
    LAG(m.total_billed_cost) OVER w  AS prev_month_billed_cost,
    CASE
        WHEN LAG(m.total_billed_cost) OVER w > 0
        THEN ROUND(
            ((m.total_billed_cost - LAG(m.total_billed_cost) OVER w)
             / LAG(m.total_billed_cost) OVER w) * 100, 2
        )
        ELSE NULL
    END AS mom_change_pct
FROM monthly m
WINDOW w AS (PARTITION BY m.tenancy_alias ORDER BY m.cost_month)
ORDER BY m.cost_month DESC;

CREATE UNIQUE INDEX idx_mv_monthly_summary
    ON mv_monthly_cost_summary (tenancy_alias, cost_month);

-- Cost by region (per-tenancy) ---------------------------------------------

CREATE MATERIALIZED VIEW mv_cost_by_region AS
SELECT
    tenancy_alias,
    date_trunc('day', chargeperiodstart)::date    AS cost_date,
    region,
    SUM(billedcost)                                AS total_billed_cost,
    SUM(effectivecost)                             AS total_effective_cost,
    COUNT(*)                                       AS line_item_count
FROM oci_finops_reports
WHERE chargecategory = 'Usage'
GROUP BY 1, 2, 3
ORDER BY 2 DESC, 4 DESC;

CREATE UNIQUE INDEX idx_mv_cost_region
    ON mv_cost_by_region (tenancy_alias, cost_date, region);

-- Daily cost by customer/team group (per-tenancy) --------------------------
-- Unmapped compartments fall through to 'Unmapped' group instead of being
-- silently grouped under 'Internal/Ops'. customer_groups is joined on
-- compartment_name alone; the user confirmed compartment names won't collide
-- across tenancies, so no composite PK is needed there.

CREATE MATERIALIZED VIEW mv_daily_cost_by_group AS
SELECT
    r.tenancy_alias,
    date_trunc('day', r.chargeperiodstart)::date     AS cost_date,
    COALESCE(g.group_name, 'Unmapped')                AS group_name,
    COALESCE(g.sub_team,   'Unmapped')                AS sub_team,
    COALESCE(g.display_name, r.oci_compartmentname)   AS display_name,
    r.oci_compartmentname                             AS compartment_name,
    r.servicename,
    r.servicecategory,
    SUM(r.billedcost)                                 AS total_billed_cost,
    SUM(r.effectivecost)                              AS total_effective_cost,
    SUM(r.listcost)                                   AS total_list_cost,
    COUNT(*)                                          AS line_item_count
FROM oci_finops_reports r
LEFT JOIN customer_groups g ON r.oci_compartmentname = g.compartment_name
WHERE r.chargecategory = 'Usage'
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
ORDER BY 2 DESC, 9 DESC;

CREATE UNIQUE INDEX idx_mv_daily_cost_group
    ON mv_daily_cost_by_group (tenancy_alias, cost_date, group_name, sub_team, compartment_name, servicename, servicecategory);

-- Refresh helper -----------------------------------------------------------

CREATE OR REPLACE FUNCTION refresh_finops_views()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_service;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_compartment;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_cost_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cost_by_region;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_group;
END;
$$;

COMMIT;
