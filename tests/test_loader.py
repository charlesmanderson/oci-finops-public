"""Tests for the PostgreSQL bulk loader.

These tests require a running PostgreSQL instance (via docker-compose).
Mark them with @pytest.mark.integration to skip in CI without a database.
"""

import pytest

from etl.focus_parser import FOCUS_COLUMNS

# Number of COPY columns = FOCUS columns + tenancy_alias + source_file
EXPECTED_COPY_COLUMNS = len(FOCUS_COLUMNS) + 2


class TestCopyColumns:
    def test_column_count(self):
        from etl.loader import COPY_COLUMNS
        assert len(COPY_COLUMNS) == EXPECTED_COPY_COLUMNS

    def test_source_file_last(self):
        from etl.loader import COPY_COLUMNS
        assert COPY_COLUMNS[-1] == "source_file"

    def test_no_auto_columns(self):
        from etl.loader import COPY_COLUMNS
        assert "id" not in COPY_COLUMNS
        assert "loaded_at" not in COPY_COLUMNS


class TestBulkLoadLogic:
    def test_empty_rows_returns_zero(self):
        """bulk_load with empty list should return 0 without touching the DB."""
        from etl.loader import bulk_load

        # We pass None for conn since it should short-circuit
        result = bulk_load(None, [], batch_size=100)
        assert result == 0
