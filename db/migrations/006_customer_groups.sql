-- 006_customer_groups.sql
-- Customer/team grouping table and materialized view for per-group cost dashboards.
-- Maps compartments to customer/team groups. The mapping rows themselves are
-- deploy-time reference data (real customer + compartment names) applied after
-- migrations from db/seed/reference_data.local.sql — not committed here.

BEGIN;

-- Reference table mapping compartments to customer/team groups
CREATE TABLE IF NOT EXISTS customer_groups (
    compartment_name  TEXT PRIMARY KEY,
    group_name        TEXT NOT NULL,
    sub_team          TEXT,
    display_name      TEXT NOT NULL
);

-- Compartment → group mappings are seeded at deploy time; see
-- db/seed/reference_data.example.sql for the template.

-- Daily cost aggregation by customer/team group
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_cost_by_group AS
SELECT
    date_trunc('day', r.chargeperiodstart)::date    AS cost_date,
    COALESCE(g.group_name, 'Internal')              AS group_name,
    COALESCE(g.sub_team, 'Ops')                     AS sub_team,
    COALESCE(g.display_name, r.oci_compartmentname) AS display_name,
    r.oci_compartmentname                           AS compartment_name,
    r.servicename,
    r.servicecategory,
    SUM(r.billedcost)                               AS total_billed_cost,
    SUM(r.effectivecost)                            AS total_effective_cost,
    SUM(r.listcost)                                 AS total_list_cost,
    COUNT(*)                                        AS line_item_count
FROM oci_finops_reports r
LEFT JOIN customer_groups g ON r.oci_compartmentname = g.compartment_name
WHERE r.chargecategory = 'Usage'
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1 DESC, 8 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_cost_group
    ON mv_daily_cost_by_group (cost_date, group_name, sub_team, compartment_name, servicename, servicecategory);

-- Update refresh function to include the new view
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
