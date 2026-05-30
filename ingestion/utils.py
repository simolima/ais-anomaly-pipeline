from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


def parse_date_from_filename(filename: str) -> Optional[date]:
    """Extract date from AIS filename pattern ais-YYYY-MM-DD.csv.zst."""
    try:
        return date(int(filename[4:8]), int(filename[9:11]), int(filename[12:14]))
    except (ValueError, IndexError):
        return None


def compute_window(
    ingested_files: set,
    window_days: int,
    end_date: date,
    default_start: date = date(2024, 1, 1),
) -> Optional[tuple]:
    """Return (start, end) for the next ingestion window, or None if complete."""
    dates = [d for f in ingested_files if (d := parse_date_from_filename(f)) is not None]
    start = max(dates) + timedelta(days=1) if dates else default_start
    if start > end_date:
        return None
    return start, min(start + timedelta(days=window_days - 1), end_date)
