"""Tests for the statistical anomaly detection module.

Integration tests require a running PostgreSQL with data loaded.
Unit tests validate the helper functions.
"""

import pytest


class TestGetRecentAnomaliesQuery:
    """Verify the query construction logic without a database."""

    def test_import(self):
        from anomaly.statistical import get_recent_anomalies, run_statistical_detection
        assert callable(get_recent_anomalies)
        assert callable(run_statistical_detection)

    def test_mark_anomalies_notified_empty(self):
        """mark_anomalies_notified with empty list should be a no-op."""
        from anomaly.statistical import mark_anomalies_notified
        # Should not raise
        mark_anomalies_notified(None, [])
