"""Scheduled anomaly detection job — runs both V1 and V2 detectors."""

from __future__ import annotations

import argparse
import logging
import os

from anomaly.notifier import send_notifications
from anomaly.statistical import get_recent_anomalies, mark_anomalies_notified, run_statistical_detection
from etl.config import AppConfig, load_config
from etl.loader import get_connection

logger = logging.getLogger(__name__)


def run_anomaly_detection(config: AppConfig, use_ml: bool = False) -> dict:
    """Run anomaly detection and send notifications.

    Returns summary dict.
    """
    summary = {"statistical_anomalies": 0, "ml_anomalies": 0, "notified": False, "errors": []}
    conn = get_connection(config.pg)

    try:
        # V1: Statistical detection
        try:
            rolling_days = int(os.environ.get("ANOMALY_ROLLING_WINDOW_DAYS", "30"))
            stddev_threshold = float(os.environ.get("ANOMALY_STDDEV_THRESHOLD", "3.0"))
            summary["statistical_anomalies"] = run_statistical_detection(
                conn, rolling_days=rolling_days, stddev_threshold=stddev_threshold
            )
        except Exception as e:
            logger.error("Statistical detection failed: %s", e, exc_info=True)
            summary["errors"].append(str(e))

        # V2: ML detection (optional)
        if use_ml:
            try:
                from anomaly.ml_detector import run_ml_detection

                contamination = float(os.environ.get("ANOMALY_ML_CONTAMINATION", "0.05"))
                summary["ml_anomalies"] = run_ml_detection(conn, contamination=contamination)
            except Exception as e:
                logger.error("ML detection failed: %s", e, exc_info=True)
                summary["errors"].append(str(e))

        # Send notifications for un-notified anomalies
        unnotified = get_recent_anomalies(conn, days=1)
        unnotified = [a for a in unnotified if not a.get("notified")]

        if unnotified:
            logger.info("Found %d un-notified anomalies", len(unnotified))
            sent = send_notifications(config.notification, unnotified)
            if sent:
                ids = [a["id"] for a in unnotified]
                mark_anomalies_notified(conn, ids)
                summary["notified"] = True

    finally:
        conn.close()

    logger.info(
        "Anomaly detection complete: %d statistical, %d ML, notified=%s",
        summary["statistical_anomalies"],
        summary["ml_anomalies"],
        summary["notified"],
    )
    return summary


def main():
    """CLI entry point for anomaly detection."""
    parser = argparse.ArgumentParser(description="OCI FinOps Anomaly Detection")
    parser.add_argument("--ml", action="store_true", help="Also run ML-based detection (requires scikit-learn)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()
    summary = run_anomaly_detection(config, use_ml=args.ml)

    if summary["errors"]:
        logger.warning("Completed with errors: %s", summary["errors"])


if __name__ == "__main__":
    main()
