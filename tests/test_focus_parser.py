"""Tests for the FOCUS report CSV parser."""

import gzip
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from etl.focus_parser import (
    FOCUS_COLUMNS,
    _coerce_value,
    _normalize_header,
    _parse_numeric,
    _parse_timestamp,
    parse_focus_csv,
    rows_to_copy_buffer,
)


class TestNormalizeHeader:
    def test_lowercase(self):
        assert _normalize_header("BilledCost") == "billedcost"

    def test_x_oci_prefix(self):
        assert _normalize_header("x_oci_ReferenceNumber") == "oci_referencenumber"

    def test_whitespace(self):
        assert _normalize_header("  ServiceName  ") == "servicename"

    def test_slash_to_underscore(self):
        assert _normalize_header("OCI/CompartmentName") == "oci_compartmentname"


class TestParseTimestamp:
    def test_iso_with_fractional_seconds(self):
        result = _parse_timestamp("2026-01-15T10:30:45.123456789+00:00")
        assert result is not None
        assert "2026-01-15" in result

    def test_iso_without_fractional(self):
        result = _parse_timestamp("2026-01-15T10:30:45+00:00")
        assert result is not None

    def test_utc_z_suffix(self):
        result = _parse_timestamp("2026-01-15T10:30:45Z")
        assert result is not None

    def test_empty_returns_none(self):
        assert _parse_timestamp("") is None
        assert _parse_timestamp("   ") is None


class TestParseNumeric:
    def test_valid_number(self):
        assert _parse_numeric("12.5") == "12.5"

    def test_zero(self):
        assert _parse_numeric("0") == "0"

    def test_negative(self):
        assert _parse_numeric("-3.14") == "-3.14"

    def test_empty_returns_none(self):
        assert _parse_numeric("") is None

    def test_invalid_returns_none(self):
        assert _parse_numeric("not-a-number") is None

    def test_whitespace_trimmed(self):
        assert _parse_numeric("  42.0  ") == "42.0"


class TestCoerceValue:
    def test_text_column(self):
        assert _coerce_value("servicename", "Compute") == "Compute"

    def test_numeric_column(self):
        assert _coerce_value("billedcost", "12.50") == "12.50"

    def test_timestamp_column(self):
        result = _coerce_value("billingperiodstart", "2026-01-15T00:00:00Z")
        assert result is not None
        assert "2026-01-15" in result

    def test_json_column(self):
        result = _coerce_value("tags", '{"env": "prod"}')
        assert result is not None
        parsed = json.loads(result)
        assert parsed["env"] == "prod"

    def test_empty_returns_none(self):
        assert _coerce_value("servicename", "") is None
        assert _coerce_value("billedcost", "") is None


class TestParseFocusCsv:
    def _make_csv_gz(self, tmp_path: Path, header: str, rows: list[str]) -> Path:
        """Helper to create a gzipped CSV file."""
        content = header + "\n" + "\n".join(rows) + "\n"
        path = tmp_path / "test_report.csv.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_parse_simple(self, tmp_path):
        header = "AvailabilityZone,BilledCost,BillingAccountId,BillingAccountName,BillingCurrency,BillingPeriodEnd,BillingPeriodStart,ChargeCategory,ChargeDescription,ChargeFrequency,ChargePeriodEnd,ChargePeriodStart,ChargeSubCategory,CommitmentDiscountCategory,CommitmentDiscountId,CommitmentDiscountName,CommitmentDiscountType,EffectiveCost,InvoiceIssuer,ListCost,ListUnitPrice,PricingCategory,PricingQuantity,PricingUnit,Provider,Publisher,Region,ResourceId,ResourceName,ResourceType,ServiceCategory,ServiceName,SkuId,SkuPriceId,SubAccountId,SubAccountName,Tags,UsageQuantity,UsageUnit,x_oci_ReferenceNumber,x_oci_CompartmentId,x_oci_CompartmentName,x_oci_OverageFlag,x_oci_UnitPriceOverage,x_oci_BilledQuantityOverage,x_oci_CostOverage,x_oci_AttributedUsage,x_oci_AttributedCost,x_oci_BackReferenceNumber"
        row = 'us-ashburn-1-AD-1,12.50,12345,MyTenancy,USD,2026-02-01T00:00:00Z,2026-01-01T00:00:00Z,Usage,Compute hours,Recurring,2026-01-02T00:00:00Z,2026-01-01T00:00:00Z,,,,,,,Oracle,12.50,12.50,OnDemand,1.00,Hours,OCI,Oracle,us-ashburn-1,ocid1.instance.oc1,my-vm,VM.Standard,Compute,Oracle Cloud Infrastructure Compute,sku123,price456,sub789,SubAcct,"{""env"":""prod""}",1.00,Hours,REF001,ocid1.compartment.oc1,Production,,0,0,0,1.00,12.50,'

        path = self._make_csv_gz(tmp_path, header, [row])
        rows = list(parse_focus_csv(path, source_file="test.csv.gz"))

        assert len(rows) == 1
        # billedcost is at index 1
        assert rows[0][1] == "12.50"
        # source_file is the last element
        assert rows[0][-1] == "test.csv.gz"

    def test_empty_file(self, tmp_path):
        path = self._make_csv_gz(tmp_path, "BilledCost,ServiceName", [])
        rows = list(parse_focus_csv(path))
        assert len(rows) == 0

    def test_tenancy_alias_emitted(self, tmp_path):
        """tenancy_alias is placed at position -2, immediately before source_file."""
        header = "BilledCost,ServiceName"
        row = "1.00,Compute"
        path = self._make_csv_gz(tmp_path, header, [row])
        rows = list(parse_focus_csv(path, source_file="s.csv.gz", tenancy_alias="customer01"))
        assert len(rows) == 1
        assert rows[0][-2] == "customer01"
        assert rows[0][-1] == "s.csv.gz"

    def test_tenancy_alias_default(self, tmp_path):
        """Default tenancy_alias is 'primary' for backward compatibility."""
        path = self._make_csv_gz(tmp_path, "BilledCost,ServiceName", ["1.00,Compute"])
        rows = list(parse_focus_csv(path, source_file="s.csv.gz"))
        assert rows[0][-2] == "primary"


class TestRowsToCopyBuffer:
    def test_basic(self):
        rows = [["val1", None, "val3"], ["a", "b", "c"]]
        buf = rows_to_copy_buffer(rows)
        lines = buf.read().strip().split("\n")
        assert len(lines) == 2
        assert "\\N" in lines[0]  # None becomes \N

    def test_tab_replacement(self):
        rows = [["has\ttab", "normal"]]
        buf = rows_to_copy_buffer(rows)
        content = buf.read()
        # Tabs in values should be replaced with spaces
        assert "\t" in content  # delimiter tabs exist
        assert "has tab" in content  # value tab was replaced
