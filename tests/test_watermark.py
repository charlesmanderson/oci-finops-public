"""Tests for the ETL watermark module."""

from etl.watermark import _human_size


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500.0 B"

    def test_kilobytes(self):
        result = _human_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = _human_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = _human_size(3 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_zero(self):
        assert _human_size(0) == "0.0 B"
