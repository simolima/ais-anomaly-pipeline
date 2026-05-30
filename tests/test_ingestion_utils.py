from datetime import date

import pytest

from ingestion.utils import compute_window, parse_date_from_filename


class TestParseDateFromFilename:
    def test_valid_filename(self):
        assert parse_date_from_filename("ais-2024-01-15.csv.zst") == date(2024, 1, 15)

    def test_end_of_year(self):
        assert parse_date_from_filename("ais-2024-12-31.csv.zst") == date(2024, 12, 31)

    def test_invalid_filename_returns_none(self):
        assert parse_date_from_filename("not-a-valid-file.csv") is None

    def test_empty_string_returns_none(self):
        assert parse_date_from_filename("") is None

    def test_truncated_filename_returns_none(self):
        assert parse_date_from_filename("ais-2024") is None


class TestComputeWindow:
    END = date(2024, 12, 31)

    def test_empty_table_starts_from_default(self):
        start, end = compute_window(set(), window_days=7, end_date=self.END)
        assert start == date(2024, 1, 1)
        assert end == date(2024, 1, 7)

    def test_advances_day_after_last_ingested(self):
        ingested = {"ais-2024-01-01.csv.zst", "ais-2024-01-02.csv.zst"}
        start, end = compute_window(ingested, window_days=7, end_date=self.END)
        assert start == date(2024, 1, 3)
        assert end == date(2024, 1, 9)

    def test_window_clamps_to_end_date(self):
        ingested = {"ais-2024-12-28.csv.zst"}
        start, end = compute_window(ingested, window_days=7, end_date=self.END)
        assert start == date(2024, 12, 29)
        assert end == date(2024, 12, 31)

    def test_returns_none_when_complete(self):
        ingested = {"ais-2024-12-31.csv.zst"}
        assert compute_window(ingested, window_days=7, end_date=self.END) is None

    def test_ignores_unrecognised_filenames(self):
        ingested = {"ais-2024-01-05.csv.zst", "some-other-file.csv"}
        start, _ = compute_window(ingested, window_days=7, end_date=self.END)
        assert start == date(2024, 1, 6)

    def test_custom_default_start(self):
        start, _ = compute_window(set(), window_days=7, end_date=self.END, default_start=date(2024, 6, 1))
        assert start == date(2024, 6, 1)
