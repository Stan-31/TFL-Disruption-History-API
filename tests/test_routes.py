from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app
from app.models import LineStatusPeriod


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def make_period(
    db_session: Session,
    *,
    line_id: str = "bakerloo",
    line_name: str = "Bakerloo",
    mode_name: str = "tube",
    status_severity: int = 10,
    status_severity_description: str = "Good Service",
    reason: str | None = None,
    started_at: datetime,
    ended_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> LineStatusPeriod:
    period = LineStatusPeriod(
        line_id=line_id,
        line_name=line_name,
        mode_name=mode_name,
        status_severity=status_severity,
        status_severity_description=status_severity_description,
        reason=reason,
        started_at=started_at,
        ended_at=ended_at,
        last_seen_at=last_seen_at or started_at,
    )
    db_session.add(period)
    db_session.flush()
    return period


def test_list_lines_returns_open_periods_ordered_by_name(
    client: TestClient, db_session: Session
) -> None:
    now = datetime.now(UTC)
    make_period(db_session, line_id="victoria", line_name="Victoria", started_at=now)
    make_period(db_session, line_id="bakerloo", line_name="Bakerloo", started_at=now)
    # A closed period shouldn't show up.
    make_period(
        db_session,
        line_id="central",
        line_name="Central",
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    response = client.get("/lines")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [line["line_id"] for line in body] == ["bakerloo", "victoria"]


def test_list_lines_empty_when_no_data(client: TestClient) -> None:
    response = client.get("/lines")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


def test_list_lines_filters_by_mode(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    make_period(
        db_session, line_id="mildmay", line_name="Mildmay", mode_name="overground", started_at=now
    )
    make_period(
        db_session, line_id="victoria", line_name="Victoria", mode_name="tube", started_at=now
    )

    response = client.get("/lines", params={"mode": "overground"})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [line["line_id"] for line in body] == ["mildmay"]


def test_list_disruptions_excludes_good_service(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    make_period(
        db_session,
        line_id="victoria",
        line_name="Victoria",
        started_at=now,
        status_severity=10,
        status_severity_description="Good Service",
    )
    make_period(
        db_session,
        line_id="central",
        line_name="Central",
        started_at=now,
        status_severity=6,
        status_severity_description="Severe Delays",
    )
    # A closed period shouldn't show up even if it was disrupted while open.
    make_period(
        db_session,
        line_id="bakerloo",
        line_name="Bakerloo",
        started_at=now - timedelta(hours=1),
        ended_at=now,
        status_severity=9,
        status_severity_description="Minor Delays",
    )

    response = client.get("/disruptions")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [line["line_id"] for line in body] == ["central"]


def test_list_disruptions_filters_by_mode(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    make_period(
        db_session,
        line_id="mildmay",
        line_name="Mildmay",
        mode_name="overground",
        started_at=now,
        status_severity=6,
        status_severity_description="Severe Delays",
    )
    make_period(
        db_session,
        line_id="central",
        line_name="Central",
        mode_name="tube",
        started_at=now,
        status_severity=6,
        status_severity_description="Severe Delays",
    )

    response = client.get("/disruptions", params={"mode": "overground"})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [line["line_id"] for line in body] == ["mildmay"]


def test_list_disruptions_empty_when_all_good_service(
    client: TestClient, db_session: Session
) -> None:
    make_period(db_session, started_at=datetime.now(UTC), status_severity=10)

    response = client.get("/disruptions")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


def test_get_line_history_404_for_unknown_line(client: TestClient) -> None:
    response = client.get("/lines/bakerloo/history")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_line_history_returns_periods_most_recent_first(
    client: TestClient, db_session: Session
) -> None:
    t0 = datetime.now(UTC) - timedelta(hours=2)
    t1 = t0 + timedelta(hours=1)
    make_period(db_session, started_at=t0, ended_at=t1, status_severity=6)
    make_period(db_session, started_at=t1, status_severity=10)

    response = client.get("/lines/bakerloo/history")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["line_id"] == "bakerloo"
    assert body["total"] == 2
    assert [item["status_severity"] for item in body["items"]] == [10, 6]


def test_get_line_history_pagination(client: TestClient, db_session: Session) -> None:
    base = datetime.now(UTC) - timedelta(days=1)
    for i in range(5):
        make_period(
            db_session,
            started_at=base + timedelta(hours=i),
            ended_at=base + timedelta(hours=i + 1),
            status_severity=i,
        )

    response = client.get("/lines/bakerloo/history", params={"limit": 2, "offset": 1})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [item["status_severity"] for item in body["items"]] == [3, 2]


def test_get_line_history_since_filter(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    make_period(db_session, started_at=now - timedelta(days=2), ended_at=now - timedelta(days=1))
    make_period(db_session, started_at=now - timedelta(hours=1))

    response = client.get(
        "/lines/bakerloo/history", params={"since": (now - timedelta(days=1)).isoformat()}
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1


def test_get_line_stats_404_for_unknown_line(client: TestClient) -> None:
    response = client.get("/lines/bakerloo/stats")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_line_stats_computes_uptime_over_full_history(
    client: TestClient, db_session: Session
) -> None:
    t0 = datetime.now(UTC) - timedelta(hours=2)
    t1 = t0 + timedelta(hours=1)
    make_period(db_session, started_at=t0, ended_at=t1, status_severity=6)
    make_period(db_session, started_at=t1, status_severity=10)

    response = client.get("/lines/bakerloo/stats")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["line_id"] == "bakerloo"
    assert body["disruption_count"] == 1
    assert body["disrupted_seconds"] == pytest.approx(3600)
    assert 0 < body["uptime_percentage"] < 100


@pytest.fixture
def with_api_key(client: TestClient) -> Iterator[None]:
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    try:
        yield
    finally:
        del app.dependency_overrides[get_settings]


def test_data_endpoint_rejects_missing_api_key(client: TestClient, with_api_key: None) -> None:
    response = client.get("/lines")
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_data_endpoint_rejects_wrong_api_key(client: TestClient, with_api_key: None) -> None:
    response = client.get("/lines", headers={"X-API-Key": "wrong"})
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_data_endpoint_accepts_correct_api_key(client: TestClient, with_api_key: None) -> None:
    response = client.get("/lines", headers={"X-API-Key": "secret"})
    assert response.status_code == HTTPStatus.OK


def test_health_endpoint_does_not_require_api_key(client: TestClient, with_api_key: None) -> None:
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK


def test_data_endpoint_open_when_no_api_key_configured(client: TestClient) -> None:
    response = client.get("/lines")
    assert response.status_code == HTTPStatus.OK
