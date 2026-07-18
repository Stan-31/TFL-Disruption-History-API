from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import LineStatusPeriod

client = TestClient(app)


def test_root_returns_service_metadata() -> None:
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["service"] == "tfl-disruption-history-api"
    assert body["status"] == "ok"


def make_period(db_session: Session, *, last_seen_at: datetime) -> None:
    db_session.add(
        LineStatusPeriod(
            line_id="bakerloo",
            line_name="Bakerloo",
            mode_name="tube",
            status_severity=10,
            status_severity_description="Good Service",
            reason=None,
            started_at=last_seen_at,
            ended_at=None,
            last_seen_at=last_seen_at,
        )
    )
    db_session.flush()


@pytest.fixture
def health_client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_degraded_when_never_polled(health_client: TestClient) -> None:
    response = health_client.get("/health")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "ok"
    assert body["last_successful_poll_at"] is None


def test_health_ok_when_recently_polled(health_client: TestClient, db_session: Session) -> None:
    make_period(db_session, last_seen_at=datetime.now(UTC))

    response = health_client.get("/health")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "ok"
    assert body["last_successful_poll_at"] is not None


def test_health_degraded_when_poll_is_stale(health_client: TestClient, db_session: Session) -> None:
    interval = get_settings().tfl_poll_interval_seconds
    make_period(db_session, last_seen_at=datetime.now(UTC) - timedelta(seconds=3 * interval + 5))

    response = health_client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "degraded"


def test_health_returns_503_when_database_unavailable() -> None:
    broken_session = MagicMock(spec=Session)
    broken_session.execute.side_effect = SQLAlchemyError("connection refused")

    def override_get_db() -> Iterator[Session]:
        yield broken_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
