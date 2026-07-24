from datetime import datetime

from sqlalchemy import DateTime, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LineStatusPeriod(Base):
    """A continuous stretch of time a line held a given status severity.

    There's one row per period, not one row per poll. `ended_at` is null while
    the period is ongoing, and a partial unique index enforces at most one open
    period per line.
    """

    __tablename__ = "line_status_periods"
    __table_args__ = (
        Index(
            "uq_line_status_periods_open",
            "line_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    line_name: Mapped[str] = mapped_column(String(128))
    mode_name: Mapped[str] = mapped_column(String(32))
    status_severity: Mapped[int] = mapped_column(SmallInteger)
    status_severity_description: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
