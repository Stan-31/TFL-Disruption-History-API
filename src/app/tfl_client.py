from collections.abc import Sequence

import httpx
from pydantic import BaseModel, ConfigDict, Field

TFL_STATUS_URL = "https://api.tfl.gov.uk/Line/Mode/{modes}/Status"


class TflLineStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status_severity: int = Field(alias="statusSeverity")
    status_severity_description: str = Field(alias="statusSeverityDescription")
    reason: str | None = None


class TflLine(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    mode_name: str = Field(alias="modeName")
    line_statuses: list[TflLineStatus] = Field(alias="lineStatuses")


async def fetch_line_statuses(
    client: httpx.AsyncClient, modes: Sequence[str], app_key: str
) -> list[TflLine]:
    url = TFL_STATUS_URL.format(modes=",".join(modes))
    # 30s, not 10s -- bus mode alone returns status for hundreds of routes,
    # much larger than the handful of lines the other modes report.
    response = await client.get(url, params={"app_key": app_key}, timeout=30.0)
    response.raise_for_status()
    return [TflLine.model_validate(item) for item in response.json()]
