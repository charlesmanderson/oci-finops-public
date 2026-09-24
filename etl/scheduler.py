"""Cron-style scheduling wrapper for the ETL pipeline, anomaly detection, and monthly reports."""

from __future__ import annotations

import logging
import signal
import sys
from datetime import date

import schedule

from etl.config import load_config
from etl.pipeline import run_etl

logger = logging.getLogger(__name__)

_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info("Received signal %d, shutting down...", signum)
    _running = False


def etl_job():
    """Scheduled ETL job."""
    logger.info("Starting scheduled ETL run...")
    try:
        config = load_config()
        summary = run_etl(config)
        logger.info("Scheduled ETL complete: %d files loaded, %d rows", summary["files_loaded"], summary["rows_loaded"])
    except Exception as e:
        logger.error("Scheduled ETL failed: %s", e, exc_info=True)


def anomaly_job():
    """Scheduled anomaly detection job."""
    logger.info("Starting scheduled anomaly detection...")
    try:
        from anomaly.runner import run_anomaly_detection

        config = load_config()
        run_anomaly_detection(config)
    except Exception as e:
        logger.error("Scheduled anomaly detection failed: %s", e, exc_info=True)


def monthly_report_job():
    """Scheduled monthly report job — runs on the 2nd of each month."""
    if date.today().day != 2:
        return
    logger.info("Starting monthly report generation...")
    try:
        from reports.monthly_report import run_monthly_report

        config = load_config()
        run_monthly_report(config)
    except Exception as e:
        logger.error("Monthly report generation failed: %s", e, exc_info=True)


def main():
    """Run the scheduler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # Schedule ETL every 6 hours
    schedule.every(6).hours.do(etl_job)

    # Schedule anomaly detection daily at 07:00
    schedule.every().day.at("07:00").do(anomaly_job)

    # Schedule monthly report daily at 07:00 (guard inside job runs only on 2nd)
    schedule.every().day.at("07:00").do(monthly_report_job)

    logger.info("Scheduler started. ETL every 6h, anomaly daily 07:00, monthly report 2nd at 07:00.")

    # Run ETL once at startup
    etl_job()

    while _running:
        schedule.run_pending()
        import time
        time.sleep(60)

    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
