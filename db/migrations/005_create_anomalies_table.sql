-- 005_create_anomalies_table.sql
-- Stores anomaly detection results from both statistical and ML-based approaches.

BEGIN;

CREATE TABLE IF NOT EXISTS cost_anomalies (
    id                BIGSERIAL       PRIMARY KEY,
    detection_date    DATE            NOT NULL,
    service_name      TEXT,
    compartment_name  TEXT,
    region            TEXT,
    metric_name       TEXT,
    metric_value      NUMERIC(20,10),
    expected_value    NUMERIC(20,10),
    deviation_score   NUMERIC,
    anomaly_type      TEXT,
    severity          TEXT,
    notified          BOOLEAN         DEFAULT FALSE,
    detected_at       TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomalies_date
    ON cost_anomalies (detection_date DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_severity
    ON cost_anomalies (severity);

CREATE INDEX IF NOT EXISTS idx_anomalies_service
    ON cost_anomalies (service_name);

CREATE INDEX IF NOT EXISTS idx_anomalies_unnotified
    ON cost_anomalies (notified) WHERE notified = FALSE;

-- SQL function for statistical anomaly detection (V1).
-- Calculates 30-day rolling average and stddev per service,
-- flags days exceeding the threshold.
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
    -- Detect cost spikes and drops
    WITH daily_costs AS (
        SELECT
            cost_date,
            servicename AS service_name,
            SUM(total_billed_cost) AS daily_cost
        FROM mv_daily_cost_by_service
        GROUP BY cost_date, servicename
    ),
    rolling_stats AS (
        SELECT
            cost_date,
            service_name,
            daily_cost,
            AVG(daily_cost) OVER w  AS rolling_avg,
            STDDEV(daily_cost) OVER w AS rolling_stddev,
            COUNT(*) OVER w          AS window_size
        FROM daily_costs
        WINDOW w AS (
            PARTITION BY service_name
            ORDER BY cost_date
            ROWS BETWEEN p_rolling_days PRECEDING AND 1 PRECEDING
        )
    ),
    anomalies AS (
        SELECT
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
        WHERE window_size >= 7  -- need at least 7 days of history
          AND rolling_stddev > 0
          AND (
              daily_cost > rolling_avg + (p_stddev_threshold * rolling_stddev)
              OR daily_cost < rolling_avg - (p_stddev_threshold * rolling_stddev)
          )
    )
    INSERT INTO cost_anomalies (detection_date, service_name, metric_name, metric_value,
                                expected_value, deviation_score, anomaly_type, severity)
    SELECT
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
    -- Avoid duplicate detections
    WHERE NOT EXISTS (
        SELECT 1 FROM cost_anomalies ca
        WHERE ca.detection_date = a.detection_date
          AND ca.service_name = a.service_name
          AND ca.metric_name = a.metric_name
    );

    GET DIAGNOSTICS v_new_rows = ROW_COUNT;
    v_inserted := v_inserted + v_new_rows;

    -- Detect brand new services (no prior history)
    INSERT INTO cost_anomalies (detection_date, service_name, metric_name, metric_value,
                                expected_value, deviation_score, anomaly_type, severity)
    SELECT
        d.cost_date,
        d.servicename,
        'daily_billed_cost',
        d.total_billed_cost,
        0,
        0,
        'new_service',
        'medium'
    FROM mv_daily_cost_by_service d
    WHERE d.cost_date = (SELECT MAX(cost_date) FROM mv_daily_cost_by_service)
      AND NOT EXISTS (
          SELECT 1 FROM mv_daily_cost_by_service prev
          WHERE prev.servicename = d.servicename
            AND prev.cost_date < d.cost_date
      )
      AND NOT EXISTS (
          SELECT 1 FROM cost_anomalies ca
          WHERE ca.detection_date = d.cost_date
            AND ca.service_name = d.servicename
            AND ca.anomaly_type = 'new_service'
      );

    GET DIAGNOSTICS v_new_rows = ROW_COUNT;
    v_inserted := v_inserted + v_new_rows;
    RETURN v_inserted;
END;
$$;

COMMIT;
