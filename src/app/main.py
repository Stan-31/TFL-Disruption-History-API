import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import get_sessionmaker
from app.poller import run_poll_loop


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


@app.get("/")
def root() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": "tfl-disruption-history-api",
        "status": "ok",
        "environment": settings.environment,
    }
