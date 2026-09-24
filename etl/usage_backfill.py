"""Provisional gap-fill of dashboard cost data from the OCI Usage API.

When a tenancy's FOCUS export stalls, this synthesizes summarized cost rows for
the missing days and loads them into oci_finops_reports tagged provisional
(source_file 'usage-api://...'). Real FOCUS data takes precedence: only days
strictly after the FOCUS frontier are filled, and provisional rows are rebuilt
every run, so FOCUS auto-replaces them as it catches up.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import oci

from etl.config import OciTenancyConfig
from etl.focus_parser import FOCUS_COLUMNS
from etl.loader import bulk_load

logger = logging.getLogger(__name__)

PROVISIONAL_PREFIX = "usage-api://"
FRONTIER_LOOKBACK_DAYS = 75  # bound the frontier query to recent partitions


def gap_days(frontier: date | None, today: date) -> list[date]:
    if frontier is None:
        return []
    out: list[date] = []
    d = frontier + timedelta(days=1)
    while d <= today:
        out.append(d)
        d += timedelta(days=1)
    return out


def focus_frontier(conn, tenancy_alias: str, today: date) -> date | None:
    lookback_month = date(today.year, today.month, 1) - timedelta(days=FRONTIER_LOOKBACK_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(chargeperiodstart)::date FROM oci_finops_reports "
            "WHERE tenancy_alias = %s AND source_file NOT LIKE %s "
            "AND billingperiodstart >= %s",
            (tenancy_alias, PROVISIONAL_PREFIX + "%", lookback_month),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def _delete_provisional(conn, tenancy_alias: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM oci_finops_reports WHERE tenancy_alias = %s AND source_file LIKE %s",
            (tenancy_alias, PROVISIONAL_PREFIX + "%"),
        )
        return cur.rowcount


@dataclass
class UsageGroup:
    service: str | None
    compartment_name: str | None
    region: str | None
    amount: float


def _synthetic_refnum(alias: str, day: date, g: UsageGroup) -> str:
    key = f"{alias}|{day.isoformat()}|{g.service}|{g.compartment_name}|{g.region}"
    return "usageapi-" + hashlib.sha1(key.encode("utf-8")).hexdigest()


def to_row(tenancy_alias: str, day: date, g: UsageGroup) -> list:
    start = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    month_start = datetime(day.year, day.month, 1, tzinfo=timezone.utc)
    amount = str(g.amount)
    values = {c: None for c in FOCUS_COLUMNS}
    values.update({
        "servicename": g.service,
        "oci_compartmentname": g.compartment_name,
        "region": g.region,
        "provider": "OCI",
        "billedcost": amount,
        "effectivecost": amount,
        "listcost": amount,
        "chargecategory": "Usage",
        "chargeperiodstart": start.isoformat(),
        "chargeperiodend": end.isoformat(),
        "billingperiodstart": month_start.isoformat(),
        "oci_referencenumber": _synthetic_refnum(tenancy_alias, day, g),
    })
    source_file = f"{PROVISIONAL_PREFIX}{tenancy_alias}/{day.isoformat()}"
    return [values[c] for c in FOCUS_COLUMNS] + [tenancy_alias, source_file]


def build_rows(tenancy_alias: str, day: date, groups: list[UsageGroup]) -> list[list]:
    return [to_row(tenancy_alias, day, g) for g in groups]


def build_usage_client(tenancy: OciTenancyConfig):
    cfg_path = Path(tenancy.config_file).expanduser()
    if cfg_path.is_file():
        return oci.usage_api.UsageapiClient(oci.config.from_file(str(cfg_path), tenancy.config_profile))
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    return oci.usage_api.UsageapiClient(config={}, signer=signer)


def fetch_usage(client, tenant_ocid: str, day: date) -> list[UsageGroup]:
    start = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    details = oci.usage_api.models.RequestSummarizedUsagesDetails(
        tenant_id=tenant_ocid,
        time_usage_started=start,
        time_usage_ended=start + timedelta(days=1),
        granularity="DAILY",
        query_type="COST",
        compartment_depth=1,
        group_by=["service", "compartmentName", "region"],
    )
    resp = client.request_summarized_usages(details)
    return [
        UsageGroup(
            service=it.service, compartment_name=it.compartment_name,
            region=it.region, amount=float(it.computed_amount or 0.0),
        )
        for it in resp.data.items
    ]


def backfill(conn, tenancies, today=None, enabled=True, client_builder=None) -> dict:
    summary = {"tenancies": []}
    if not enabled:
        logger.info("Usage-API backfill disabled")
        return summary
    if today is None:
        today = datetime.now(timezone.utc).date()
    builder = client_builder or build_usage_client

    for t in tenancies:
        rec = {"tenancy": t.alias, "gap_days": 0, "rows": 0, "error": None}
        try:
            _delete_provisional(conn, t.alias)
            frontier = focus_frontier(conn, t.alias, today)
            days = gap_days(frontier, today)
            rec["gap_days"] = len(days)
            all_rows: list[list] = []
            if days:
                client = builder(t)
                for day in days:
                    all_rows.extend(build_rows(t.alias, day, fetch_usage(client, t.tenancy_ocid, day)))
            if all_rows:
                bulk_load(conn, all_rows)   # stages+inserts+COMMITS (commits the delete too)
                rec["rows"] = len(all_rows)
            else:
                conn.commit()               # commit the provisional delete
            logger.info("[%s] usage backfill: frontier=%s gap_days=%d rows=%d",
                        t.alias, frontier, len(days), rec["rows"])
        except Exception as e:
            conn.rollback()
            rec["error"] = str(e)
            logger.error("[%s] usage backfill failed: %s", t.alias, e, exc_info=True)
        summary["tenancies"].append(rec)
    return summary
