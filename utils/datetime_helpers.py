"""Shared utility helpers for the intelligence pipeline."""

from datetime import datetime, timezone


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to UTC-aware.

    SQLite returns naive datetimes; PostgreSQL returns aware ones.
    This helper ensures all datetimes are UTC-aware before arithmetic.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
