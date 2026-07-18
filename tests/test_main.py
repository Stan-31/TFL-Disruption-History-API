from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_service_metadata() -> None:
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["service"] == "tfl-disruption-history-api"
    assert body["status"] == "ok"
