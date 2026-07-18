from datetime import UTC, datetime, timedelta

import pytest

from app.models import LineStatusPeriod
from app.stats import compute_line_stats

WINDOW_START = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 1, 2, tzinfo=UTC)  # 24h window


def make_period(
    *, status_severity: int, started_at: datetime, ended_at: datetime | None
) -> LineStatusPeriod:
    return LineStatusPeriod(
        line_id="bakerloo",
        line_name="Bakerloo",
        mode_name="tube",
        status_severity=status_severity,
        status_severity_description="Good Service" if status_severity == 10 else "Disrupted",
        reason=None,
        started_at=started_at,
        ended_at=ended_at,
        last_seen_at=ended_at or started_at,
    )


def test_full_window_good_service_is_100_percent_uptime() -> None:
    period = make_period(status_severity=10, started_at=WINDOW_START, ended_at=WINDOW_END)

    result = compute_line_stats([period], window_start=WINDOW_START, window_end=WINDOW_END)

    assert result.total_seconds == 86400
    assert result.disrupted_seconds == 0
    assert result.disruption_count == 0
    assert result.uptime_percentage == 100.0


def test_disruption_fully_inside_window_counts() -> None:
    good = make_period(
        status_severity=10,
        started_at=WINDOW_START,
        ended_at=WINDOW_START + timedelta(hours=23),
    )
    disrupted = make_period(
        status_severity=6,
        started_at=WINDOW_START + timedelta(hours=23),
        ended_at=WINDOW_END,
    )

    result = compute_line_stats([good, disrupted], window_start=WINDOW_START, window_end=WINDOW_END)

    assert result.total_seconds == 86400
    assert result.disrupted_seconds == 3600
    assert result.disruption_count == 1
    assert result.uptime_percentage == pytest.approx(95.8333, abs=1e-3)


def test_period_starting_before_window_is_clipped() -> None:
    period = make_period(
        status_severity=10,
        started_at=WINDOW_START - timedelta(days=10),
        ended_at=WINDOW_START + timedelta(hours=12),
    )

    result = compute_line_stats([period], window_start=WINDOW_START, window_end=WINDOW_END)

    assert result.total_seconds == 12 * 3600


def test_ongoing_period_is_clipped_to_window_end() -> None:
    period = make_period(status_severity=10, started_at=WINDOW_START, ended_at=None)

    result = compute_line_stats([period], window_start=WINDOW_START, window_end=WINDOW_END)

    assert result.total_seconds == 86400


def test_empty_window_returns_100_percent_uptime_without_division_error() -> None:
    result = compute_line_stats([], window_start=WINDOW_START, window_end=WINDOW_START)

    assert result.total_seconds == 0
    assert result.disruption_count == 0
    assert result.uptime_percentage == 100.0
