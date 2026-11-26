from datetime import UTC, datetime


class SystemClock:
    """UTC wall clock used by production repositories."""

    def now(self) -> datetime:
        return datetime.now(UTC)
