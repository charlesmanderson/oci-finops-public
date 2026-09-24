"""V1 statistical anomaly detection using PostgreSQL window functions."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_statistical_detection(
    conn,
    rolling_days: int = 30,
    stddev_threshold: float = 3.0,
) -> int:
    """Run the SQL-based statistical anomaly detection function.

    Uses 30-day rolling average + stddev to detect cost spikes and drops.
    Also detects brand new services with no prior history.

    Returns the number of new anomalies detected.
    """
    logger.info(
        "Running statistical anomaly detection (window=%d days, threshold=%.1f stddev)",
        rolling_days,
        stddev_threshold,
    )

    with conn.cursor() as cur:
        cur.execute("SELECT detect_cost_anomalies(%s, %s)", (rolling_days, stddev_threshold))
        result = cur.fetchone()
        anomaly_count = result[0] if result else 0

    conn.commit()
    logger.info("Statistical detection found %d new anomalies", anomaly_count)
    return anomaly_count


def get_recent_anomalies(conn, days: int = 7, severity: str | None = None) -> list[dict]:
    """Fetch recent anomalies for notification purposes (across all tenancies)."""
    query = """
        SELECT id, tenancy_alias, detection_date, service_name, compartment_name, region,
               metric_name, metric_value, expected_value, deviation_score,
               anomaly_type, severity, notified
        FROM cost_anomalies
        WHERE detection_date >= CURRENT_DATE - %s * interval '1 day'
    """
    params: list = [days]

    if severity:
        query += " AND severity = %s"
        params.append(severity)

    query += " ORDER BY tenancy_alias, detection_date DESC, severity DESC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def mark_anomalies_notified(conn, anomaly_ids: list[int]) -> None:
    """Mark anomalies as notified after sending alerts."""
    if not anomaly_ids:
        return

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE cost_anomalies SET notified = TRUE WHERE id = ANY(%s)",
            (anomaly_ids,),
        )
    conn.commit()
    logger.info("Marked %d anomalies as notified", len(anomaly_ids))
