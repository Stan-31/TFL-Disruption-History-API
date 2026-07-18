from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import LineStatusPeriod
from app.poller import (
    MAX_BACKOFF_SECONDS,
    LineObservation,
    apply_observations,
    next_backoff_seconds,
)


def make_observation(status_severity: int = 10, reason: str | None = None) -> LineObservation:
    return LineObservation(
        line_id="bakerloo",
        line_name="Bakerloo",
        mode_name="tube",
        status_severity=status_severity,
        status_severity_description="Good Service" if status_severity == 10 else "Disrupted",
        reason=reason,
    )


def test_first_poll_opens_a_period(db_session: Session) -> None:
    now = datetime.now(UTC)
    apply_observations(db_session, [make_observation()], now=now)
    db_session.flush()

    periods = db_session.execute(select(LineStatusPeriod)).scalars().all()
    assert len(periods) == 1
    assert periods[0].line_id == "bakerloo"
    assert periods[0].started_at == now
    assert periods[0].ended_at is None
    assert periods[0].last_seen_at == now


def test_same_status_bumps_last_seen_at_without_new_row(db_session: Session) -> None:
    t0 = datetime.now(UTC)
    apply_observations(db_session, [make_observation()], now=t0)
    db_session.flush()

    t1 = t0 + timedelta(minutes=1)
    apply_observations(db_session, [make_observation()], now=t1)
    db_session.flush()

    periods = db_session.execute(select(LineStatusPeriod)).scalars().all()
    assert len(periods) == 1
    assert periods[0].last_seen_at == t1
    assert periods[0].ended_at is None


def test_status_change_closes_old_period_and_opens_new(db_session: Session) -> None:
    t0 = datetime.now(UTC)
    apply_observations(db_session, [make_observation(status_severity=10)], now=t0)
    db_session.flush()

    t1 = t0 + timedelta(minutes=1)
    apply_observations(
        db_session, [make_observation(status_severity=6, reason="Severe delays")], now=t1
    )
    db_session.flush()

    periods = (
        db_session.execute(select(LineStatusPeriod).order_by(LineStatusPeriod.started_at))
        .scalars()
        .all()
    )
    assert len(periods) == 2
    assert periods[0].ended_at == t1
    assert periods[0].status_severity == 10
    assert periods[1].started_at == t1
    assert periods[1].ended_at is None
    assert periods[1].status_severity == 6


def test_partial_unique_index_prevents_two_open_periods(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        LineStatusPeriod(
            line_id="bakerloo",
            line_name="Bakerloo",
            mode_name="tube",
            status_severity=10,
            status_severity_description="Good Service",
            reason=None,
            started_at=now,
            ended_at=None,
            last_seen_at=now,
        )
    )
    db_session.flush()

    db_session.add(
        LineStatusPeriod(
            line_id="bakerloo",
            line_name="Bakerloo",
            mode_name="tube",
            status_severity=6,
            status_severity_description="Severe Delays",
            reason=None,
            started_at=now,
            ended_at=None,
            last_seen_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_next_backoff_seconds_no_backoff_below_two_failures() -> None:
    assert next_backoff_seconds(60, 0) == 60
    assert next_backoff_seconds(60, 1) == 60


def test_next_backoff_seconds_doubles_on_repeated_failures() -> None:
    assert next_backoff_seconds(60, 2) == 120
    assert next_backoff_seconds(60, 3) == 240
    assert next_backoff_seconds(60, 4) == 480


def test_next_backoff_seconds_caps_at_max() -> None:
    assert next_backoff_seconds(60, 20) == MAX_BACKOFF_SECONDS
