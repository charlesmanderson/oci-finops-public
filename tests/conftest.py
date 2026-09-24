"""Shared pytest fixtures for OCI FinOps tests."""

import gzip
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_focus_csv_gz():
    """Path to the sample gzipped FOCUS report fixture."""
    return FIXTURES_DIR / "sample_focus_report.csv.gz"


@pytest.fixture
def sample_focus_rows():
    """A few parsed rows as they'd appear after focus_parser processing."""
    return [
        {
            "servicename": "Oracle Cloud Infrastructure Compute",
            "billedcost": "12.5000000000",
            "billingperiodstart": "2026-01-15T00:00:00+00:00",
            "region": "us-ashburn-1",
            "oci_compartmentname": "Production",
            "chargecategory": "Usage",
        },
        {
            "servicename": "Oracle Cloud Infrastructure Object Storage",
            "billedcost": "0.2500000000",
            "billingperiodstart": "2026-01-15T00:00:00+00:00",
            "region": "us-ashburn-1",
            "oci_compartmentname": "Development",
            "chargecategory": "Usage",
        },
    ]


@pytest.fixture
def pg_dsn():
    """PostgreSQL DSN for test database (requires running local postgres)."""
    return (
        f"host={os.environ.get('PG_HOST', 'localhost')} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ.get('PG_DATABASE', 'oci_finops')} "
        f"user={os.environ.get('PG_USER', 'finops')} "
        f"password={os.environ.get('PG_PASSWORD', 'changeme')}"
    )
