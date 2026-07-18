from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title="TfL Disruption History API", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": "tfl-disruption-history-api",
        "status": "ok",
        "environment": settings.environment,
    }
