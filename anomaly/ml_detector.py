"""V2 ML-based anomaly detection using scikit-learn Isolation Forest."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np

logger = logging.getLogger(__name__)


def _fetch_training_data(conn, lookback_days: int = 90) -> list[dict]:
    """Fetch daily cost data for model training, across all tenancies."""
    query = """
        SELECT
            tenancy_alias,
            cost_date,
            servicename AS service_name,
            total_billed_cost AS daily_cost
        FROM mv_daily_cost_by_service
        WHERE cost_date >= CURRENT_DATE - %s * interval '1 day'
        ORDER BY tenancy_alias, cost_date, service_name
    """
    with conn.cursor() as cur:
        cur.execute(query, (lookback_days,))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _build_feature_matrix(records: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """Build feature vectors from daily cost records.

    Features per record:
        - daily_cost: the raw cost
        - day_of_week: 0 (Mon) through 6 (Sun)
        - month: 1-12
        - trailing_7d_avg: average cost over the previous 7 days for this
          (tenancy, service) — trailing averages are kept tenancy-scoped so a
          spike in service X in one tenancy doesn't move the baseline for
          service X in another tenancy.
    """
    from collections import defaultdict

    # Group by (tenancy, service)
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        by_key[(r["tenancy_alias"], r["service_name"])].append(r)

    features = []
    metadata = []

    for (tenancy_alias, service_name), rows in by_key.items():
        rows.sort(key=lambda r: r["cost_date"])
        costs = [float(r["daily_cost"]) for r in rows]

        for i, row in enumerate(rows):
            cost = costs[i]
            cost_date = row["cost_date"]
            dow = cost_date.weekday() if isinstance(cost_date, date) else 0
            month = cost_date.month if isinstance(cost_date, date) else 1

            start = max(0, i - 7)
            trailing = costs[start:i] if i > 0 else [cost]
            trailing_avg = sum(trailing) / len(trailing) if trailing else cost

            features.append([cost, dow, month, trailing_avg])
            metadata.append({
                "tenancy_alias": tenancy_alias,
                "cost_date": cost_date,
                "service_name": service_name,
                "daily_cost": cost,
                "trailing_avg": trailing_avg,
            })

    return np.array(features) if features else np.empty((0, 4)), metadata


def run_ml_detection(
    conn,
    lookback_days: int = 90,
    contamination: float = 0.05,
) -> int:
    """Run Isolation Forest anomaly detection on daily cost data.

    Returns the number of new anomalies inserted.
    """
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        logger.error("scikit-learn is not installed. Install with: pip install scikit-learn")
        return 0

    logger.info(
        "Running ML anomaly detection (lookback=%d days, contamination=%.2f)",
        lookback_days,
        contamination,
    )

    records = _fetch_training_data(conn, lookback_days)
    if not records:
        logger.warning("No training data available")
        return 0

    features, metadata = _build_feature_matrix(records)
    if features.shape[0] < 10:
        logger.warning("Insufficient training data: %d records", features.shape[0])
        return 0

    # Scale features
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    # Train Isolation Forest
    model = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100,
    )
    predictions = model.fit_predict(features_scaled)
    scores = model.decision_function(features_scaled)

    # Filter to anomalies from each tenancy's most recent day (tenancies can
    # have different freshness if loads run at different times).
    latest_by_tenancy: dict[str, "date"] = {}
    for m in metadata:
        ta = m["tenancy_alias"]
        if ta not in latest_by_tenancy or m["cost_date"] > latest_by_tenancy[ta]:
            latest_by_tenancy[ta] = m["cost_date"]
    inserted = 0

    for i, (pred, score, meta) in enumerate(zip(predictions, scores, metadata)):
        if pred == -1 and meta["cost_date"] == latest_by_tenancy.get(meta["tenancy_alias"]):
            deviation = abs(float(score))
            if deviation < 0.01:
                severity = "low"
            elif deviation < 0.05:
                severity = "medium"
            elif deviation < 0.1:
                severity = "high"
            else:
                severity = "critical"

            anomaly_type = "spike" if meta["daily_cost"] > meta["trailing_avg"] else "drop"

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cost_anomalies
                        (tenancy_alias, detection_date, service_name, metric_name, metric_value,
                         expected_value, deviation_score, anomaly_type, severity)
                    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM cost_anomalies
                        WHERE tenancy_alias = %s
                          AND detection_date = %s
                          AND service_name = %s
                          AND metric_name = 'daily_billed_cost_ml'
                    )
                    """,
                    (
                        meta["tenancy_alias"],
                        meta["cost_date"],
                        meta["service_name"],
                        "daily_billed_cost_ml",
                        meta["daily_cost"],
                        meta["trailing_avg"],
                        round(deviation, 4),
                        anomaly_type,
                        severity,
                        meta["tenancy_alias"],
                        meta["cost_date"],
                        meta["service_name"],
                    ),
                )
                inserted += cur.rowcount

    conn.commit()
    logger.info("ML detection found %d new anomalies across tenancies: %s", inserted, latest_by_tenancy)
    return inserted
