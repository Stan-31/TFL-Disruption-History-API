from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models import LineStatusPeriod

# TfL's statusSeverity code for "Good Service" -- long-stable and
# well-documented. This is an intentional, narrow exception to "don't
# hardcode severity meanings" (see poller.py): a disruption-stats endpoint
# can't avoid drawing this one line somewhere.
GOOD_SERVICE_SEVERITY = 10


@dataclass(frozen=True)
class LineStatsResult:
    total_seconds: float
    disrupted_seconds: float
    disruption_count: int
    uptime_percentage: float


def compute_line_stats(
    periods: Sequence[LineStatusPeriod], *, window_start: datetime, window_end: datetime
) -> LineStatsResult:
    total_seconds = 0.0
    disrupted_seconds = 0.0
    disruption_count = 0

    for period in periods:
        start = max(period.started_at, window_start)
        end = min(period.ended_at or window_end, window_end)
        if end <= start:
            continue

        duration = (end - start).total_seconds()
        total_seconds += duration
        if period.status_severity != GOOD_SERVICE_SEVERITY:
            disrupted_seconds += duration
            disruption_count += 1

    uptime_percentage = (
        100.0 * (total_seconds - disrupted_seconds) / total_seconds if total_seconds > 0 else 100.0
    )

    return LineStatsResult(
        total_seconds=total_seconds,
        disrupted_seconds=disrupted_seconds,
        disruption_count=disruption_count,
        uptime_percentage=uptime_percentage,
    )
