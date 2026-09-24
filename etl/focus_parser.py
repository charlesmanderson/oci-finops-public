"""CSV parsing and type coercion for OCI FOCUS cost reports."""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Ordered list of columns matching the database schema (excluding id, loaded_at, source_file)
FOCUS_COLUMNS = [
    "availabilityzone",
    "billedcost",
    "billingaccountid",
    "billingaccountname",
    "billingcurrency",
    "billingperiodend",
    "billingperiodstart",
    "chargecategory",
    "chargedescription",
    "chargefrequency",
    "chargeperiodend",
    "chargeperiodstart",
    "chargesubcategory",
    "commitmentdiscountcategory",
    "commitmentdiscountid",
    "commitmentdiscountname",
    "commitmentdiscounttype",
    "effectivecost",
    "invoiceissuer",
    "listcost",
    "listunitprice",
    "pricingcategory",
    "pricingquantity",
    "pricingunit",
    "provider",
    "publisher",
    "region",
    "resourceid",
    "resourcename",
    "resourcetype",
    "servicecategory",
    "servicename",
    "skuid",
    "skupriceid",
    "subaccountid",
    "subaccountname",
    "tags",
    "usagequantity",
    "usageunit",
    "oci_referencenumber",
    "oci_compartmentid",
    "oci_compartmentname",
    "oci_overageflag",
    "oci_unitpriceoverage",
    "oci_billedquantityoverage",
    "oci_costoverage",
    "oci_attributedusage",
    "oci_attributedcost",
    "oci_backreferencenumber",
]

# Columns that should be parsed as NUMERIC
NUMERIC_COLUMNS = {
    "billedcost", "effectivecost", "listcost", "listunitprice",
    "pricingquantity", "usagequantity",
    "oci_unitpriceoverage", "oci_billedquantityoverage",
    "oci_costoverage", "oci_attributedusage", "oci_attributedcost",
}

# Columns that should be parsed as BIGINT
BIGINT_COLUMNS = {"billingaccountid"}

# Columns that should be parsed as TIMESTAMPTZ
TIMESTAMP_COLUMNS = {
    "billingperiodend", "billingperiodstart",
    "chargeperiodend", "chargeperiodstart",
}

# Columns that should be parsed as JSONB
JSON_COLUMNS = {"tags"}

# Timestamp formats seen in OCI FOCUS reports
TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
]


def _parse_timestamp(value: str) -> str | None:
    """Parse a timestamp string into ISO 8601 format for PostgreSQL."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    logger.warning("Could not parse timestamp: %s", value)
    return value


def _parse_numeric(value: str) -> str | None:
    """Parse a numeric string, returning a string suitable for COPY."""
    if not value or not value.strip():
        return None
    try:
        Decimal(value.strip())
        return value.strip()
    except InvalidOperation:
        logger.warning("Could not parse numeric value: %s", value)
        return None


def _parse_bigint(value: str) -> str | None:
    """Parse a bigint string."""
    if not value or not value.strip():
        return None
    try:
        return str(int(value.strip()))
    except ValueError:
        logger.warning("Could not parse bigint value: %s", value)
        return None


def _parse_json(value: str) -> str | None:
    """Parse and validate a JSON value."""
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        parsed = json.loads(value)
        return json.dumps(parsed)
    except json.JSONDecodeError:
        logger.warning("Could not parse JSON value: %.100s", value)
        return None


def _coerce_value(column: str, value: str) -> str | None:
    """Coerce a raw CSV value to the appropriate type for its column."""
    if not value or not value.strip():
        return None

    value = value.strip()

    if column in TIMESTAMP_COLUMNS:
        return _parse_timestamp(value)
    if column in NUMERIC_COLUMNS:
        return _parse_numeric(value)
    if column in BIGINT_COLUMNS:
        return _parse_bigint(value)
    if column in JSON_COLUMNS:
        return _parse_json(value)
    return value


def _normalize_header(header: str) -> str:
    """Normalize a CSV header name to match our column names.

    OCI FOCUS reports use mixed case and sometimes include slashes
    for the OCI-specific columns (e.g., 'x_oci_ReferenceNumber').
    """
    h = header.strip().lower()
    # Handle x_oci_ prefix variants
    h = h.replace("x_oci_", "oci_")
    h = h.replace("/", "_")
    h = h.replace(" ", "_")
    h = h.replace("-", "")
    return h


def parse_focus_csv(
    file_path: Path,
    source_file: str | None = None,
    tenancy_alias: str = "primary",
) -> Generator[list[Any], None, int]:
    """Parse a gzipped FOCUS CSV file and yield rows ready for COPY loading.

    Each yielded row is a list of values in FOCUS_COLUMNS order, followed by
    tenancy_alias and then source_file. Returns the total row count via the
    generator return value.

    tenancy_alias defaults to 'primary' for backward compatibility with
    older single-tenancy callers; the multi-tenancy pipeline passes it
    explicitly per tenancy.
    """
    row_count = 0
    opener = gzip.open if str(file_path).endswith(".gz") else open

    with opener(file_path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)

        if reader.fieldnames is None:
            logger.error("No header found in %s", file_path)
            return 0

        # Build a mapping from normalized CSV header → original header
        header_map: dict[str, str] = {}
        for orig in reader.fieldnames:
            normalized = _normalize_header(orig)
            header_map[normalized] = orig

        missing = set(FOCUS_COLUMNS) - set(header_map.keys())
        if missing:
            logger.warning("Missing columns in %s: %s", file_path, missing)

        for raw_row in reader:
            row: list[str | None] = []
            for col in FOCUS_COLUMNS:
                orig_header = header_map.get(col)
                raw_value = raw_row.get(orig_header, "") if orig_header else ""
                row.append(_coerce_value(col, raw_value))
            row.append(tenancy_alias)
            row.append(source_file or str(file_path))
            yield row
            row_count += 1

    logger.info("Parsed %d rows from %s (tenancy=%s)", row_count, file_path, tenancy_alias)
    return row_count


def _escape_copy_value(v: Any) -> str:
    """Escape a value for PostgreSQL COPY TEXT format.

    COPY uses backslash as an escape character (\\n = newline, \\t = tab,
    \\\\ = literal backslash, \\N = NULL).  We must double any backslashes
    in values so that sequences like JSON's \\n aren't misinterpreted.
    """
    if v is None:
        return "\\N"
    s = str(v)
    s = s.replace("\r", " ").replace("\n", " ")  # strip real control chars
    s = s.replace("\\", "\\\\")                  # double backslashes for COPY
    s = s.replace("\t", " ")                      # tabs are column delimiters
    return s


def rows_to_copy_buffer(rows: list[list[Any]]) -> io.StringIO:
    """Convert parsed rows into a tab-delimited StringIO buffer for COPY FROM STDIN."""
    buf = io.StringIO()
    for row in rows:
        line = "\t".join(_escape_copy_value(v) for v in row)
        buf.write(line + "\n")
    buf.seek(0)
    return buf
