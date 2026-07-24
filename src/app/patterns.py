from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import LineStatusPeriod
from app.stats import GOOD_SERVICE_SEVERITY

LONDON_TZ = ZoneInfo("Europe/London")

DAYS_OF_WEEK: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# (start_hour, end_hour) in Europe/London local time, evaluated per calendar day.
# evening_night's end_hour is less than its start_hour, meaning it wraps into the
# next calendar day (19:00 today to 07:00 tomorrow) but is attributed to today's
# weekday, matching how someone would actually say "Monday night".
TIME_BUCKETS: dict[str, tuple[int, int]] = {
    "am_peak": (7, 10),
    "midday": (10, 16),
    "pm_peak": (16, 19),
    "evening_night": (19, 7),
}


@dataclass(frozen=True)
class PatternCell:
    day_of_week: str
    time_bucket: str
    total_seconds: float
    disrupted_seconds: float
    weeks_observed: int

    @property
    def uptime_percentage(self) -> float:
        if self.total_seconds == 0:
            return 100.0
        return 100.0 * (self.total_seconds - self.disrupted_seconds) / self.total_seconds


def _bucket_bounds_for_day(day: date, bucket: str) -> tuple[datetime, datetime]:
    """Absolute UTC start/end of one occurrence of `bucket` on the given local calendar day.

    Converts to UTC immediately rather than returning Europe/London-attached
    datetimes: subtracting two aware datetimes that carry *different* UTC
    offsets (e.g. one GMT, one BST either side of a clock change) does not
    reliably yield the correct elapsed duration. Stored periods are already
    UTC, so doing all overlap arithmetic in UTC on both sides avoids ever
    subtracting across a mismatched offset.
    """
    start_hour, end_hour = TIME_BUCKETS[bucket]
    start = datetime.combine(day, time(hour=start_hour), tzinfo=LONDON_TZ)
    end_day = day + timedelta(days=1) if end_hour <= start_hour else day
    end = datetime.combine(end_day, time(hour=end_hour), tzinfo=LONDON_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def compute_line_patterns(
    periods: Sequence[LineStatusPeriod], *, now: datetime
) -> list[PatternCell]:
    """Break a line's full period history into a day-of-week x time-of-day grid.

    Each stored period gets intersected against every recurring bucket instance
    (e.g. every Monday 07:00-10:00 Europe/London) it overlaps, so a period
    spanning weeks contributes to every matching day it actually covers rather
    than being attributed to a single point in time. Periods are contiguous and
    gapless (see poller.apply_observations), so summing every period's overlap
    into a bucket gives that bucket's true total elapsed time, with no separate
    pass needed to compute the denominator.
    """
    totals: dict[tuple[str, str], float] = defaultdict(float)
    disrupted: dict[tuple[str, str], float] = defaultdict(float)
    days_seen: dict[tuple[str, str], set[date]] = defaultdict(set)

    for period in periods:
        period_start = period.started_at
        period_end = period.ended_at or now
        if period_end <= period_start:
            continue

        # Start one day early: the previous day's evening_night bucket runs past
        # midnight into this day's early hours, so a period beginning at, say,
        # 03:00 can still overlap it. Starting the walk from the period's own
        # start date alone would silently drop that overlap.
        day = period_start.astimezone(LONDON_TZ).date() - timedelta(days=1)
        last_day = period_end.astimezone(LONDON_TZ).date()
        while day <= last_day:
            weekday_name = DAYS_OF_WEEK[day.weekday()]
            for bucket_name in TIME_BUCKETS:
                bucket_start, bucket_end = _bucket_bounds_for_day(day, bucket_name)
                overlap_start = max(period_start, bucket_start)
                overlap_end = min(period_end, bucket_end)
                if overlap_end <= overlap_start:
                    continue

                overlap_seconds = (overlap_end - overlap_start).total_seconds()
                key = (weekday_name, bucket_name)
                totals[key] += overlap_seconds
                days_seen[key].add(day)
                if period.status_severity != GOOD_SERVICE_SEVERITY:
                    disrupted[key] += overlap_seconds
            day += timedelta(days=1)

    return [
        PatternCell(
            day_of_week=weekday_name,
            time_bucket=bucket_name,
            total_seconds=totals[(weekday_name, bucket_name)],
            disrupted_seconds=disrupted[(weekday_name, bucket_name)],
            weeks_observed=len(days_seen[(weekday_name, bucket_name)]),
        )
        for weekday_name in DAYS_OF_WEEK
        for bucket_name in TIME_BUCKETS
    ]
