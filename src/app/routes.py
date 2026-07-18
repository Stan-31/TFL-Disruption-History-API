from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LineStatusPeriod
from app.schemas import LineHistoryPage, LineStats, LineStatusPeriodOut, LineSummary
from app.stats import compute_line_stats

router = APIRouter()


@router.get("/lines", response_model=list[LineSummary])
def list_lines(db: Session = Depends(get_db)) -> list[LineStatusPeriod]:
    stmt = (
        select(LineStatusPeriod)
        .where(LineStatusPeriod.ended_at.is_(None))
        .order_by(LineStatusPeriod.line_name)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/lines/{line_id}/history", response_model=LineHistoryPage)
def get_line_history(
    line_id: str,
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> LineHistoryPage:
    latest = db.execute(
        select(LineStatusPeriod)
        .where(LineStatusPeriod.line_id == line_id)
        .order_by(LineStatusPeriod.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Unknown line_id: {line_id}")

    filters = [LineStatusPeriod.line_id == line_id]
    if since is not None:
        filters.append(LineStatusPeriod.started_at >= since)

    total = db.execute(
        select(func.count()).select_from(LineStatusPeriod).where(*filters)
    ).scalar_one()
    items = (
        db.execute(
            select(LineStatusPeriod)
            .where(*filters)
            .order_by(LineStatusPeriod.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return LineHistoryPage(
        line_id=latest.line_id,
        line_name=latest.line_name,
        mode_name=latest.mode_name,
        total=total,
        limit=limit,
        offset=offset,
        items=[LineStatusPeriodOut.model_validate(item) for item in items],
    )


@router.get("/lines/{line_id}/stats", response_model=LineStats)
def get_line_stats(
    line_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
) -> LineStats:
    latest = db.execute(
        select(LineStatusPeriod)
        .where(LineStatusPeriod.line_id == line_id)
        .order_by(LineStatusPeriod.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Unknown line_id: {line_id}")

    window_end = until or datetime.now(UTC)
    if since is not None:
        window_start = since
    else:
        window_start = db.execute(
            select(func.min(LineStatusPeriod.started_at)).where(LineStatusPeriod.line_id == line_id)
        ).scalar_one()

    periods = (
        db.execute(
            select(LineStatusPeriod).where(
                LineStatusPeriod.line_id == line_id,
                LineStatusPeriod.started_at < window_end,
                or_(
                    LineStatusPeriod.ended_at.is_(None),
                    LineStatusPeriod.ended_at > window_start,
                ),
            )
        )
        .scalars()
        .all()
    )

    result = compute_line_stats(periods, window_start=window_start, window_end=window_end)

    return LineStats(
        line_id=latest.line_id,
        line_name=latest.line_name,
        mode_name=latest.mode_name,
        window_start=window_start,
        window_end=window_end,
        total_seconds=result.total_seconds,
        disrupted_seconds=result.disrupted_seconds,
        uptime_percentage=round(result.uptime_percentage, 2),
        disruption_count=result.disruption_count,
    )
