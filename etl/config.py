"""Environment-based configuration for the ETL pipeline."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OciTenancyConfig:
    """One OCI tenancy's connection settings. Multiple instances coexist
    during multi-tenancy ETL runs; each maps to a profile in ~/.oci/config."""
    alias: str
    tenancy_ocid: str
    region: str
    config_profile: str
    namespace: str = "bling"
    config_file: str = field(default_factory=lambda: os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))

    @property
    def bucket_name(self) -> str:
        return self.tenancy_ocid


@dataclass(frozen=True)
class PgConfig:
    host: str = field(default_factory=lambda: os.environ.get("PG_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("PG_PORT", "5432")))
    database: str = field(default_factory=lambda: os.environ.get("PG_DATABASE", "oci_finops"))
    user: str = field(default_factory=lambda: os.environ.get("PG_USER", "finops"))
    password: str = field(default_factory=lambda: os.environ.get("PG_PASSWORD", "changeme"))

    @property
    def dsn(self) -> str:
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"


@dataclass(frozen=True)
class EtlConfig:
    batch_size: int = field(default_factory=lambda: int(os.environ.get("ETL_BATCH_SIZE", "10000")))
    temp_dir: Path = field(default_factory=lambda: Path(os.environ.get("ETL_TEMP_DIR", "/tmp/oci-finops")))
    focus_report_year: str | None = field(default_factory=lambda: os.environ.get("FOCUS_REPORT_YEAR"))
    usage_api_backfill: bool = field(
        default_factory=lambda: os.environ.get("USAGE_API_BACKFILL", "1").lower()
        not in ("0", "false", "no", "")
    )

    def __post_init__(self):
        self.temp_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class NotificationConfig:
    ons_topic_ocid: str | None = field(default_factory=lambda: os.environ.get("ONS_TOPIC_OCID") or None)
    smtp_host: str | None = field(default_factory=lambda: os.environ.get("SMTP_HOST") or None)
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_user: str | None = field(default_factory=lambda: os.environ.get("SMTP_USER") or None)
    smtp_password: str | None = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD") or None)
    smtp_from: str = field(default_factory=lambda: os.environ.get("SMTP_FROM", "finops-alerts@example.com"))
    smtp_to: str = field(default_factory=lambda: os.environ.get("SMTP_TO", ""))


@dataclass(frozen=True)
class AppConfig:
    pg: PgConfig = field(default_factory=PgConfig)
    etl: EtlConfig = field(default_factory=EtlConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)


def load_config() -> AppConfig:
    return AppConfig()


def load_tenancies(conn) -> list[OciTenancyConfig]:
    """Load active tenancies from the database.

    If OCI_TENANCY_OCID is set, returns a single-tenancy override list
    (useful for --init-db before migration 009 has run, or for ad-hoc loads
    pinned to one tenancy). Otherwise queries the tenancies table.
    """
    env_ocid = os.environ.get("OCI_TENANCY_OCID")
    if env_ocid:
        logger.info("OCI_TENANCY_OCID set in env — using single-tenancy override")
        return [OciTenancyConfig(
            alias=os.environ.get("OCI_TENANCY_ALIAS", "default"),
            tenancy_ocid=env_ocid,
            region=os.environ.get("OCI_REGION", "us-ashburn-1"),
            config_profile=os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"),
            namespace=os.environ.get("OCI_NAMESPACE", "bling"),
        )]

    with conn.cursor() as cur:
        cur.execute("""
            SELECT alias, tenancy_ocid, home_region, config_profile, namespace
              FROM tenancies
             WHERE is_active
             ORDER BY alias
        """)
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError(
            "No active tenancies found. Run `python -m etl.pipeline --init-db` "
            "to create the tenancies table, or set OCI_TENANCY_OCID in the environment."
        )

    return [
        OciTenancyConfig(
            alias=r[0], tenancy_ocid=r[1], region=r[2], config_profile=r[3], namespace=r[4],
        )
        for r in rows
    ]
