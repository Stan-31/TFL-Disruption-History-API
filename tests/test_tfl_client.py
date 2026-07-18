import httpx
import pytest

from app.tfl_client import fetch_line_statuses

SAMPLE_RESPONSE = [
    {
        "id": "bakerloo",
        "name": "Bakerloo",
        "modeName": "tube",
        "lineStatuses": [
            {
                "statusSeverity": 10,
                "statusSeverityDescription": "Good Service",
                "reason": None,
            }
        ],
    },
    {
        "id": "central",
        "name": "Central",
        "modeName": "tube",
        "lineStatuses": [
            {
                "statusSeverity": 9,
                "statusSeverityDescription": "Minor Delays",
                "reason": "Central Line: Minor delays due to an earlier signal failure.",
            },
            {
                "statusSeverity": 20,
                "statusSeverityDescription": "Service Closed",
                "reason": None,
            },
        ],
    },
]


@pytest.mark.anyio
async def test_fetch_line_statuses_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/Line/Mode/tube/Status"
        assert request.url.params["app_key"] == "test-key"
        return httpx.Response(200, json=SAMPLE_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        lines = await fetch_line_statuses(client, ["tube"], "test-key")

    assert len(lines) == 2
    assert lines[0].id == "bakerloo"
    assert lines[0].mode_name == "tube"
    assert lines[0].line_statuses[0].status_severity == 10

    assert len(lines[1].line_statuses) == 2
    assert lines[1].line_statuses[1].status_severity_description == "Service Closed"


@pytest.mark.anyio
async def test_fetch_line_statuses_raises_on_error_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_line_statuses(client, ["tube"], "bad-key")
