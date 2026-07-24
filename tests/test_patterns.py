from datetime import UTC, datetime, timedelta

import pytest

from app.models import LineStatusPeriod
from app.patterns import LONDON_TZ, PatternCell, compute_line_patterns

# 2026-06-01 is a Monday, well inside BST (UK clocks are UTC+1).
A_MONDAY = datetime(2026, 6, 1, tzinfo=LONDON_TZ)


def make_period(
    *, status_severity: int, started_at: datetime, ended_at: datetime | None
) -> LineStatusPeriod:
    return LineStatusPeriod(
        line_id="central",
        line_name="Central",
        mode_name="tube",
        status_severity=status_severity,
        status_severity_description="Good Service" if status_severity == 10 else "Disrupted",
        reason=None,
        started_at=started_at,
        ended_at=ended_at,
        last_seen_at=ended_at or started_at,
    )


def cell_for(cells: list[PatternCell], day_of_week: str, time_bucket: str) -> PatternCell:
    return next(c for c in cells if c.day_of_week == day_of_week and c.time_bucket == time_bucket)


def test_period_within_single_bucket_counts_only_that_cell() -> None:
    period = make_period(
        status_severity=6,
        started_at=A_MONDAY.replace(hour=8),
        ended_at=A_MONDAY.replace(hour=9),
    )

    cells = compute_line_patterns([period], now=A_MONDAY.replace(hour=9))

    am_peak = cell_for(cells, "monday", "am_peak")
    assert am_peak.total_seconds == 3600
    assert am_peak.disrupted_seconds == 3600
    assert am_peak.weeks_observed == 1
    assert all(c.total_seconds == 0 for c in cells if c is not am_peak)


def test_boundary_between_buckets_splits_without_double_counting() -> None:
    # Straddles the am_peak/midday boundary at 10:00 by one minute either side.
    period = make_period(
        status_severity=10,
        started_at=A_MONDAY.replace(hour=9, minute=59),
        ended_at=A_MONDAY.replace(hour=10, minute=1),
    )

    cells = compute_line_patterns([period], now=A_MONDAY.replace(hour=10, minute=1))

    am_peak = cell_for(cells, "monday", "am_peak")
    midday = cell_for(cells, "monday", "midday")
    assert am_peak.total_seconds == 60
    assert midday.total_seconds == 60
    assert sum(c.total_seconds for c in cells) == 120


def test_evening_night_wraps_past_midnight_attributed_to_starting_day() -> None:
    # 23:00 Monday to 01:00 Tuesday should land entirely under Monday's
    # evening_night bucket, not Tuesday's.
    period = make_period(
        status_severity=10,
        started_at=A_MONDAY.replace(hour=23),
        ended_at=A_MONDAY.replace(hour=23) + timedelta(hours=2),
    )

    cells = compute_line_patterns([period], now=A_MONDAY.replace(hour=23) + timedelta(hours=2))

    monday_night = cell_for(cells, "monday", "evening_night")
    tuesday_night = cell_for(cells, "tuesday", "evening_night")
    assert monday_night.total_seconds == 7200
    assert tuesday_night.total_seconds == 0


def test_period_starting_in_small_hours_attributes_to_previous_days_evening_night() -> None:
    # A period from 03:00-05:00 Monday falls inside *Sunday's* evening_night
    # bucket (Sun 19:00 - Mon 07:00), not any of Monday's own buckets, all of
    # which start at 07:00 or later. A day-walk that only starts from the
    # period's own start date would miss this entirely.
    period = make_period(
        status_severity=10,
        started_at=A_MONDAY.replace(hour=3),
        ended_at=A_MONDAY.replace(hour=5),
    )

    cells = compute_line_patterns([period], now=A_MONDAY.replace(hour=5))

    sunday_night = cell_for(cells, "sunday", "evening_night")
    assert sunday_night.total_seconds == 7200
    assert all(c.total_seconds == 0 for c in cells if c is not sunday_night)


def test_period_spanning_multiple_days_distributes_across_each_day() -> None:
    # Covers Monday and Tuesday entirely, extended to Wed 07:00 so Tuesday's
    # evening_night bucket (which itself reaches into Wed 07:00) is fully, not
    # just partially, covered.
    period = make_period(
        status_severity=10,
        started_at=A_MONDAY,
        ended_at=A_MONDAY + timedelta(days=2, hours=7),
    )

    cells = compute_line_patterns([period], now=A_MONDAY + timedelta(days=2, hours=7))

    monday_total = sum(c.total_seconds for c in cells if c.day_of_week == "monday")
    tuesday_total = sum(c.total_seconds for c in cells if c.day_of_week == "tuesday")
    assert monday_total == 86400
    assert tuesday_total == 86400
    assert cell_for(cells, "monday", "am_peak").weeks_observed == 1


def test_open_period_is_clipped_to_now() -> None:
    period = make_period(status_severity=10, started_at=A_MONDAY.replace(hour=8), ended_at=None)

    cells = compute_line_patterns([period], now=A_MONDAY.replace(hour=9))

    assert cell_for(cells, "monday", "am_peak").total_seconds == 3600


def test_uptime_percentage_mixes_disrupted_and_good_service() -> None:
    good = make_period(
        status_severity=10,
        started_at=A_MONDAY.replace(hour=7),
        ended_at=A_MONDAY.replace(hour=8, minute=30),
    )
    disrupted = make_period(
        status_severity=6,
        started_at=A_MONDAY.replace(hour=8, minute=30),
        ended_at=A_MONDAY.replace(hour=10),
    )

    cells = compute_line_patterns([good, disrupted], now=A_MONDAY.replace(hour=10))

    am_peak = cell_for(cells, "monday", "am_peak")
    assert am_peak.total_seconds == 10800  # 3 hours
    assert am_peak.disrupted_seconds == 5400  # 1.5 hours
    assert am_peak.uptime_percentage == pytest.approx(50.0)


def test_empty_history_returns_100_percent_everywhere_without_division_error() -> None:
    cells = compute_line_patterns([], now=A_MONDAY)

    assert all(c.total_seconds == 0 for c in cells)
    assert all(c.uptime_percentage == 100.0 for c in cells)


def test_dst_spring_forward_day_has_23_real_hours() -> None:
    # 2026-03-29 is the day UK clocks spring forward (01:00 -> 02:00 local), so
    # the calendar day itself only contains 23 hours of real elapsed time. The
    # missing hour falls in *Saturday's* evening_night bucket (Sat 19:00-Sun
    # 07:00), not any of Sunday's own buckets, since none of them start before
    # 07:00 -- so the total across Saturday-night plus all of Sunday should
    # still land on exactly 23h, not 24h.
    start = datetime(2026, 3, 29, 0, 0, tzinfo=LONDON_TZ)
    end = datetime(2026, 3, 30, 0, 0, tzinfo=LONDON_TZ)
    period = make_period(status_severity=10, started_at=start, ended_at=end)

    cells = compute_line_patterns([period], now=end)

    saturday_night = cell_for(cells, "saturday", "evening_night")
    sunday_total = sum(c.total_seconds for c in cells if c.day_of_week == "sunday")
    assert saturday_night.total_seconds + sunday_total == pytest.approx(23 * 3600)


def test_periods_use_utc_input_correctly() -> None:
    # started_at/ended_at come out of the DB as UTC-aware; in June (BST, UTC+1)
    # 07:00 UTC is 08:00 London time, still inside am_peak.
    period = make_period(
        status_severity=10,
        started_at=datetime(2026, 6, 1, 7, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
    )

    cells = compute_line_patterns([period], now=datetime(2026, 6, 1, 8, 0, tzinfo=UTC))

    assert cell_for(cells, "monday", "am_peak").total_seconds == 3600
