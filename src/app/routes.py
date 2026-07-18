from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LineStatusPeriod
from app.schemas import LineHistoryPage, LineStatusPeriodOut, LineSummary

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
