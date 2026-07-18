import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, get_sessionmaker
from app.models import LineStatusPeriod
from app.poller import run_poll_loop
from app.routes import router
from app.schemas import HealthStatus


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    poll_task = asyncio.create_task(
        run_poll_loop(
            session_factory=get_sessionmaker(),
            modes=settings.tfl_modes.split(","),
            app_key=settings.tfl_app_key,
            interval_seconds=settings.tfl_poll_interval_seconds,
        )
    )
    try:
        yield
    finally:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task


app = FastAPI(title="TfL Disruption History API", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": "tfl-disruption-history-api",
        "status": "ok",
        "environment": settings.environment,
    }


@app.get("/health", response_model=HealthStatus)
def health(db: Session = Depends(get_db)) -> HealthStatus:
    settings = get_settings()
    try:
        last_successful_poll_at = db.execute(
            select(func.max(LineStatusPeriod.last_seen_at))
        ).scalar_one()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    stale_after = timedelta(seconds=3 * settings.tfl_poll_interval_seconds)
    is_stale = (
        last_successful_poll_at is None or datetime.now(UTC) - last_successful_poll_at > stale_after
    )

    return HealthStatus(
        status="degraded" if is_stale else "ok",
        database="ok",
        last_successful_poll_at=last_successful_poll_at,
        poll_interval_seconds=settings.tfl_poll_interval_seconds,
    )
