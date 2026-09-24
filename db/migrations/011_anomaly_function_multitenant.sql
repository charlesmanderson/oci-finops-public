-- 011_anomaly_function_multitenant.sql
-- Replace detect_cost_anomalies() so anomalies are detected per-tenancy.
-- A spike in service X in one tenancy shouldn't affect the rolling average
-- used to flag anomalies in service X in another tenancy.

BEGIN;

CREATE OR REPLACE FUNCTION detect_cost_anomalies(
    p_rolling_days INT DEFAULT 30,
    p_stddev_threshold NUMERIC DEFAULT 3.0
)
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    v_inserted INT := 0;
    v_new_rows INT;
BEGIN
    -- Spikes and drops, partitioned by (tenancy_alias, service_name)
    WITH daily_costs AS (
        SELECT
            tenancy_alias,
            cost_date,
            servicename AS service_name,
            SUM(total_billed_cost) AS daily_cost
        FROM mv_daily_cost_by_service
        GROUP BY tenancy_alias, cost_date, servicename
    ),
    rolling_stats AS (
        SELECT
            tenancy_alias,
            cost_date,
            service_name,
            daily_cost,
            AVG(daily_cost)    OVER w AS rolling_avg,
            STDDEV(daily_cost) OVER w AS rolling_stddev,
            COUNT(*)           OVER w AS window_size
        FROM daily_costs
        WINDOW w AS (
            PARTITION BY tenancy_alias, service_name
            ORDER BY cost_date
            ROWS BETWEEN p_rolling_days PRECEDING AND 1 PRECEDING
        )
    ),
    anomalies AS (
        SELECT
            tenancy_alias,
            cost_date            AS detection_date,
            service_name,
            'daily_billed_cost'  AS metric_name,
            daily_cost           AS metric_value,
            rolling_avg          AS expected_value,
            CASE
                WHEN rolling_stddev > 0
                THEN (daily_cost - rolling_avg) / rolling_stddev
                ELSE 0
            END                  AS deviation_score,
            CASE
                WHEN daily_cost > rolling_avg + (p_stddev_threshold * COALESCE(rolling_stddev, 0))
                THEN 'spike'
                WHEN daily_cost < rolling_avg - (p_stddev_threshold * COALESCE(rolling_stddev, 0))
                THEN 'drop'
            END                  AS anomaly_type
        FROM rolling_stats
        WHERE window_size >= 7
          AND rolling_stddev > 0
          AND (
              daily_cost > rolling_avg + (p_stddev_threshold * rolling_stddev)
              OR daily_cost < rolling_avg - (p_stddev_threshold * rolling_stddev)
          )
    )
    INSERT INTO cost_anomalies (tenancy_alias, detection_date, service_name, metric_name,
                                metric_value, expected_value, deviation_score, anomaly_type, severity)
    SELECT
        a.tenancy_alias,
        a.detection_date,
        a.service_name,
        a.metric_name,
        a.metric_value,
        a.expected_value,
        a.deviation_score,
        a.anomaly_type,
        CASE
            WHEN ABS(a.deviation_score) >= 5 THEN 'critical'
            WHEN ABS(a.deviation_score) >= 4 THEN 'high'
            WHEN ABS(a.deviation_score) >= 3 THEN 'medium'
            ELSE 'low'
        END AS severity
    FROM anomalies a
    WHERE NOT EXISTS (
        SELECT 1 FROM cost_anomalies ca
        WHERE ca.tenancy_alias  = a.tenancy_alias
          AND ca.detection_date = a.detection_date
          AND ca.service_name   = a.service_name
          AND ca.metric_name    = a.metric_name
    );

    GET DIAGNOSTICS v_new_rows = ROW_COUNT;
    v_inserted := v_inserted + v_new_rows;

    -- Brand new services (no prior history), per-tenancy
    INSERT INTO cost_anomalies (tenancy_alias, detection_date, service_name, metric_name,
                                metric_value, expected_value, deviation_score, anomaly_type, severity)
    SELECT
        d.tenancy_alias,
        d.cost_date,
        d.servicename,
        'daily_billed_cost',
        d.total_billed_cost,
        0,
        0,
        'new_service',
        'medium'
    FROM mv_daily_cost_by_service d
    WHERE d.cost_date = (
        SELECT MAX(cost_date) FROM mv_daily_cost_by_service mx
        WHERE mx.tenancy_alias = d.tenancy_alias
    )
      AND NOT EXISTS (
          SELECT 1 FROM mv_daily_cost_by_service prev
          WHERE prev.tenancy_alias = d.tenancy_alias
            AND prev.servicename   = d.servicename
            AND prev.cost_date     < d.cost_date
      )
      AND NOT EXISTS (
          SELECT 1 FROM cost_anomalies ca
          WHERE ca.tenancy_alias  = d.tenancy_alias
            AND ca.detection_date = d.cost_date
            AND ca.service_name   = d.servicename
            AND ca.anomaly_type   = 'new_service'
      );

    GET DIAGNOSTICS v_new_rows = ROW_COUNT;
    v_inserted := v_inserted + v_new_rows;
    RETURN v_inserted;
END;
$$;

COMMIT;
