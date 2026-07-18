from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LineSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: str
    line_name: str
    mode_name: str
    status_severity: int
    status_severity_description: str
    reason: str | None
    started_at: datetime
    last_seen_at: datetime


class LineStatusPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status_severity: int
    status_severity_description: str
    reason: str | None
    started_at: datetime
    ended_at: datetime | None
    last_seen_at: datetime


class LineHistoryPage(BaseModel):
    line_id: str
    line_name: str
    mode_name: str
    total: int
    limit: int
    offset: int
    items: list[LineStatusPeriodOut]


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok"]
    last_successful_poll_at: datetime | None
    poll_interval_seconds: int
