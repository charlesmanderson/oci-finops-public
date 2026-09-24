"""ETL watermark tracking — records which files have been loaded, per tenancy."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_loaded_files(conn, tenancy_alias: str) -> set[str]:
    """Return the set of file paths that have been successfully loaded for this tenancy."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT file_path FROM etl_watermark WHERE tenancy_alias = %s AND status = 'success'",
            (tenancy_alias,),
        )
        return {row[0] for row in cur.fetchall()}


def mark_loaded(
    conn,
    tenancy_alias: str,
    file_path: str,
    file_size: int,
    row_count: int,
    status: str = "success",
) -> None:
    """Record a file as loaded in the watermark table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermark (tenancy_alias, file_path, file_size, loaded_at, row_count, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenancy_alias, file_path) DO UPDATE SET
                file_size = EXCLUDED.file_size,
                loaded_at = EXCLUDED.loaded_at,
                row_count = EXCLUDED.row_count,
                status = EXCLUDED.status
            """,
            (tenancy_alias, file_path, file_size, datetime.now(timezone.utc), row_count, status),
        )
    conn.commit()
    logger.info(
        "Watermark %s [%s]: %s (%d rows, %s)",
        status, tenancy_alias, file_path, row_count, _human_size(file_size),
    )


def mark_failed(conn, tenancy_alias: str, file_path: str, file_size: int) -> None:
    """Record a file as failed in the watermark table."""
    mark_loaded(conn, tenancy_alias, file_path, file_size, row_count=0, status="failed")


def get_watermark_summary(conn) -> dict:
    """Return summary statistics from the watermark table, grouped by tenancy and status."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                tenancy_alias,
                status,
                COUNT(*) AS file_count,
                COALESCE(SUM(row_count), 0) AS total_rows,
                COALESCE(SUM(file_size), 0) AS total_bytes
            FROM etl_watermark
            GROUP BY tenancy_alias, status
            ORDER BY tenancy_alias, status
        """)
        summary: dict = {}
        for row in cur.fetchall():
            tenancy, status, file_count, total_rows, total_bytes = row
            summary.setdefault(tenancy, {})[status] = {
                "file_count": file_count,
                "total_rows": total_rows,
                "total_bytes": total_bytes,
            }
        return summary


def _human_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
