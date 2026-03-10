"""Tests for source_config.py — include/exclude filtering and validity dates."""

from __future__ import annotations

from pathlib import Path

from src.ingestion.source_config import SourceConfig, extract_validity_dates


class TestSourceConfigDiscovery:
    def test_discovers_all_supported_files(self, tmp_path):
        (tmp_path / "doc.pdf").touch()
        (tmp_path / "sheet.xlsx").touch()
        (tmp_path / "image.jpg").touch()
        source = SourceConfig(root=tmp_path)
        files = source.discover_files()
        names = {f.name for f in files}
        assert "doc.pdf" in names
        assert "sheet.xlsx" not in names  # PDF-only
        assert "image.jpg" not in names

    def test_include_patterns_filter(self, tmp_path):
        rates = tmp_path / "Rates"
        rates.mkdir()
        (rates / "rate_card.pdf").touch()
        (tmp_path / "brochure.pdf").touch()

        source = SourceConfig(root=tmp_path, include_patterns=["Rates/**/*.pdf"])
        files = source.discover_files()
        names = {f.name for f in files}
        assert "rate_card.pdf" in names
        assert "brochure.pdf" not in names

    def test_exclude_patterns_filter(self, tmp_path):
        (tmp_path / "info.pdf").touch()
        logos = tmp_path / "Logo"
        logos.mkdir()
        (logos / "logo.pdf").touch()

        source = SourceConfig(root=tmp_path, exclude_patterns=["**/Logo*/**"])
        files = source.discover_files()
        names = {f.name for f in files}
        assert "info.pdf" in names
        assert "logo.pdf" not in names

    def test_include_and_exclude_combined(self, tmp_path):
        props = tmp_path / "Properties" / "1. Hotel - City"
        props.mkdir(parents=True)
        (props / "Brochure.pdf").touch()
        logos = props / "Logo"
        logos.mkdir()
        (logos / "logo.pdf").touch()

        source = SourceConfig(
            root=tmp_path,
            include_patterns=["Properties/**/*.pdf"],
            exclude_patterns=["**/Logo*/**"],
        )
        files = source.discover_files()
        names = {f.name for f in files}
        assert "Brochure.pdf" in names
        assert "logo.pdf" not in names

    def test_nonexistent_root_returns_empty(self):
        source = SourceConfig(root=Path("/nonexistent/path"))
        assert source.discover_files() == []

    def test_empty_directory(self, tmp_path):
        source = SourceConfig(root=tmp_path)
        assert source.discover_files() == []


class TestExtractValidityDates:
    def test_full_date_range(self):
        result = extract_validity_dates("RACK Rates La Fontaine Oct 2025 - 08 Jan 2027.pdf")
        assert result["valid_from"] == "2025-10"
        assert result["valid_to"] == "2027-01"

    def test_year_only_range(self):
        result = extract_validity_dates("POD Rack Rates (2025 - 2026).pdf")
        assert result["valid_from"] == "2025-01"
        assert result["valid_to"] == "2026-12"

    def test_year_and_word(self):
        result = extract_validity_dates("RACK Rates Oyster Box 2025 and 2026.pdf")
        assert result["valid_from"] == "2025-01"
        assert result["valid_to"] == "2026-12"

    def test_no_dates(self):
        result = extract_validity_dates("Brochure.pdf")
        assert result == {}

    def test_single_year_no_match(self):
        result = extract_validity_dates("Rates 2025.pdf")
        assert result == {}

    def test_en_dash_separator(self):
        result = extract_validity_dates("CFT Rates 2025 \u2013Jan 2027.pdf")
        assert result["valid_from"] == "2025-01"
        assert result["valid_to"] == "2027-01"
