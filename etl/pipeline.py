"""Main ETL orchestrator — coordinates file discovery, parsing, and loading
across one or more OCI tenancies."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from etl.config import AppConfig, OciTenancyConfig, load_config, load_tenancies
from etl.focus_parser import parse_focus_csv
from etl.loader import bulk_load, get_connection, refresh_materialized_views, run_migrations, run_seed
from etl.oci_client import OciObjectStorageClient
from etl.usage_backfill import backfill
from etl.watermark import get_loaded_files, mark_failed, mark_loaded

logger = logging.getLogger(__name__)


def _run_etl_for_tenancy(
    conn,
    tenancy: OciTenancyConfig,
    config: AppConfig,
    dry_run: bool,
    backfill: bool,
) -> dict:
    """Run the ETL pipeline for a single tenancy. Caller manages the DB connection
    and runs refresh_materialized_views once across all tenancies."""
    summary = {
        "tenancy": tenancy.alias,
        "files_found": 0, "files_skipped": 0, "files_loaded": 0, "rows_loaded": 0,
        "errors": [],
    }

    loaded_files = get_loaded_files(conn, tenancy.alias) if not backfill else set()
    logger.info("[%s] Watermark: %d files previously loaded", tenancy.alias, len(loaded_files))

    oci_client = OciObjectStorageClient(tenancy)
    report_files = oci_client.list_focus_reports(year=config.etl.focus_report_year)
    summary["files_found"] = len(report_files)

    new_files = [f for f in report_files if f.name not in loaded_files]
    summary["files_skipped"] = len(report_files) - len(new_files)
    logger.info(
        "[%s] New files to load: %d (skipping %d already loaded)",
        tenancy.alias, len(new_files), summary["files_skipped"],
    )

    if dry_run:
        logger.info("=== DRY RUN [%s] — would load these files: ===", tenancy.alias)
        for f in new_files:
            logger.info("  %s (%d bytes)", f.name, f.size)
        return summary

    for report_file in new_files:
        try:
            logger.info("[%s] Processing: %s", tenancy.alias, report_file.name)

            local_path = oci_client.download_file(report_file.name, config.etl.temp_dir)

            rows = list(parse_focus_csv(
                local_path, source_file=report_file.name, tenancy_alias=tenancy.alias,
            ))
            row_count = len(rows)

            if row_count == 0:
                logger.warning("No rows parsed from %s, skipping", report_file.name)
                mark_loaded(conn, tenancy.alias, report_file.name, report_file.size, 0, status="empty")
                continue

            loaded = bulk_load(conn, rows, batch_size=config.etl.batch_size)
            mark_loaded(conn, tenancy.alias, report_file.name, report_file.size, loaded)

            summary["files_loaded"] += 1
            summary["rows_loaded"] += loaded
            logger.info("[%s] Loaded %d rows from %s", tenancy.alias, loaded, report_file.name)

            local_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error("[%s] Failed to process %s: %s", tenancy.alias, report_file.name, e, exc_info=True)
            summary["errors"].append({"tenancy": tenancy.alias, "file": report_file.name, "error": str(e)})
            conn.rollback()
            mark_failed(conn, tenancy.alias, report_file.name, report_file.size)

    return summary


def run_etl(config: AppConfig, dry_run: bool = False, force_reload: bool = False) -> dict:
    """Run the ETL pipeline across all active tenancies.

    Returns:
        Aggregate summary dict with per-tenancy summaries under 'tenancies'.
    """
    aggregate = {
        "tenancies": [],
        "files_found": 0, "files_skipped": 0, "files_loaded": 0, "rows_loaded": 0,
        "errors": [],
    }

    conn = get_connection(config.pg)
    try:
        tenancies = load_tenancies(conn)
        logger.info("Loaded %d active tenancies: %s", len(tenancies), [t.alias for t in tenancies])

        for tenancy in tenancies:
            try:
                t_summary = _run_etl_for_tenancy(conn, tenancy, config, dry_run, force_reload)
            except Exception as e:
                logger.error("[%s] Tenancy ETL failed entirely: %s", tenancy.alias, e, exc_info=True)
                conn.rollback()
                t_summary = {
                    "tenancy": tenancy.alias,
                    "files_found": 0, "files_skipped": 0, "files_loaded": 0, "rows_loaded": 0,
                    "errors": [{"tenancy": tenancy.alias, "file": "<tenancy>", "error": str(e)}],
                }
            aggregate["tenancies"].append(t_summary)
            for k in ("files_found", "files_skipped", "files_loaded", "rows_loaded"):
                aggregate[k] += t_summary[k]
            aggregate["errors"].extend(t_summary["errors"])

        bf_rows = 0
        if not dry_run:
            try:
                bf = backfill(conn, tenancies, enabled=config.etl.usage_api_backfill)
                aggregate["usage_backfill"] = bf
                bf_rows = sum(r["rows"] for r in bf["tenancies"])
            except Exception as e:
                logger.error("Usage-API backfill failed: %s", e, exc_info=True)

        if (aggregate["files_loaded"] > 0 or bf_rows > 0) and not dry_run:
            try:
                refresh_materialized_views(conn)
            except Exception as e:
                logger.error("Failed to refresh materialized views: %s", e, exc_info=True)
                aggregate["errors"].append({"file": "materialized_views", "error": str(e)})
    finally:
        conn.close()

    logger.info("=== ETL Summary ===")
    for t_summary in aggregate["tenancies"]:
        logger.info(
            "  [%s] found=%d skipped=%d loaded=%d rows=%d errors=%d",
            t_summary["tenancy"], t_summary["files_found"], t_summary["files_skipped"],
            t_summary["files_loaded"], t_summary["rows_loaded"], len(t_summary["errors"]),
        )
    logger.info(
        "  TOTAL    found=%d skipped=%d loaded=%d rows=%d errors=%d",
        aggregate["files_found"], aggregate["files_skipped"],
        aggregate["files_loaded"], aggregate["rows_loaded"], len(aggregate["errors"]),
    )
    if aggregate["errors"]:
        for err in aggregate["errors"]:
            logger.warning("    %s", err)

    return aggregate


def init_database(config: AppConfig) -> None:
    """Run database migrations to initialize the schema."""
    conn = get_connection(config.pg)
    try:
        run_migrations(conn)
    finally:
        conn.close()


def seed_database(config: AppConfig) -> None:
    """Apply deploy-time reference data (db/seed/*.local.sql) after migrations."""
    conn = get_connection(config.pg)
    try:
        run_seed(conn)
    finally:
        conn.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="OCI FinOps ETL Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="List files to load without loading them")
    parser.add_argument("--backfill", action="store_true", help="Re-load all files (ignore watermark)")
    parser.add_argument("--init-db", action="store_true", help="Run database migrations")
    parser.add_argument("--seed", action="store_true", help="Apply deploy-time reference data (db/seed/*.local.sql)")
    parser.add_argument("--year", type=str, help="Filter reports by year (overrides FOCUS_REPORT_YEAR)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()

    if args.year:
        config = AppConfig(
            pg=config.pg,
            etl=type(config.etl)(
                batch_size=config.etl.batch_size,
                temp_dir=config.etl.temp_dir,
                focus_report_year=args.year,
            ),
            notification=config.notification,
        )

    if args.init_db:
        logger.info("Initializing database...")
        init_database(config)
        logger.info("Database initialized")

    if args.seed:
        logger.info("Applying reference data seed...")
        seed_database(config)
        logger.info("Reference data applied")

    if args.init_db or args.seed:
        return

    summary = run_etl(config, dry_run=args.dry_run, force_reload=args.backfill)

    if summary["errors"] and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
