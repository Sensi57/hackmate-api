from datetime import datetime, timezone


def to_naive_utc(dt: datetime) -> datetime:
    """Normalise aware/naive datetimes so they can be safely compared."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
