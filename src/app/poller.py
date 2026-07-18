import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import LineStatusPeriod
from app.tfl_client import TflLine, TflLineStatus, fetch_line_statuses

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LineObservation:
    line_id: str
    line_name: str
    mode_name: str
    status_severity: int
    status_severity_description: str
    reason: str | None


def primary_status(line: TflLine) -> TflLineStatus:
    """Pick a single status for a line that reports multiple concurrently.

    Deterministic tie-break on the lowest statusSeverity value. TfL's severity
    scale isn't a strict "worse is lower" ordering across its full range, so
    this is a known simplification -- good enough while a line usually only
    reports one status at a time.
    """
    return min(line.line_statuses, key=lambda status: status.status_severity)


def to_observations(lines: Iterable[TflLine]) -> list[LineObservation]:
    observations = []
    for line in lines:
        if not line.line_statuses:
            logger.warning("Line %s returned no statuses, skipping", line.id)
            continue
        status = primary_status(line)
        observations.append(
            LineObservation(
                line_id=line.id,
                line_name=line.name,
                mode_name=line.mode_name,
                status_severity=status.status_severity,
                status_severity_description=status.status_severity_description,
                reason=status.reason,
            )
        )
    return observations


def apply_observations(
    session: Session, observations: Iterable[LineObservation], *, now: datetime
) -> None:
    for observation in observations:
        open_period = session.execute(
            select(LineStatusPeriod).where(
                LineStatusPeriod.line_id == observation.line_id,
                LineStatusPeriod.ended_at.is_(None),
            )
        ).scalar_one_or_none()

        if open_period is None:
            session.add(
                LineStatusPeriod(
                    line_id=observation.line_id,
                    line_name=observation.line_name,
                    mode_name=observation.mode_name,
                    status_severity=observation.status_severity,
                    status_severity_description=observation.status_severity_description,
                    reason=observation.reason,
                    started_at=now,
                    ended_at=None,
                    last_seen_at=now,
                )
            )
            continue

        if open_period.status_severity == observation.status_severity:
            open_period.last_seen_at = now
            open_period.line_name = observation.line_name
            open_period.status_severity_description = observation.status_severity_description
            open_period.reason = observation.reason
            continue

        open_period.ended_at = now
        session.add(
            LineStatusPeriod(
                line_id=observation.line_id,
                line_name=observation.line_name,
                mode_name=observation.mode_name,
                status_severity=observation.status_severity,
                status_severity_description=observation.status_severity_description,
                reason=observation.reason,
                started_at=now,
                ended_at=None,
                last_seen_at=now,
            )
        )


def _poll_once(session_factory: sessionmaker[Session], observations: list[LineObservation]) -> None:
    with session_factory() as session:
        apply_observations(session, observations, now=datetime.now(UTC))
        session.commit()


async def run_poll_loop(
    *,
    session_factory: sessionmaker[Session],
    modes: Sequence[str],
    app_key: str,
    interval_seconds: int,
) -> None:
    async with httpx.AsyncClient() as client:
        while True:
            try:
                lines = await fetch_line_statuses(client, modes, app_key)
                observations = to_observations(lines)
                await asyncio.to_thread(_poll_once, session_factory, observations)
                logger.info("Polled %d line(s)", len(observations))
            except Exception:
                logger.exception("Poll iteration failed, will retry next interval")
            await asyncio.sleep(interval_seconds)
