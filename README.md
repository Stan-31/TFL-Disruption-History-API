# TfL Disruption History API

TfL's Unified API only exposes *current* line status -- there's no history endpoint.
This service polls it on a schedule, persists every observation, and exposes the
historical record TfL doesn't: how often each line is disrupted, when, for how long,
and with what severity.

Status: **Phase 1** -- repo skeleton, settings, docker-compose, CI. No database
schema or polling yet (see later phases).

## Stack

Python 3.12, FastAPI, PostgreSQL (SQLAlchemy 2.x + Alembic), pytest, Docker /
docker-compose, GitHub Actions.

## Running locally

```
cp .env.example .env
# edit .env and set TFL_APP_KEY (a placeholder is fine for Phase 1)
docker compose up --build
```

Then visit http://localhost:8000/ -- you should see:

```json
{"service": "tfl-disruption-history-api", "status": "ok", "environment": "local"}
```

## Tests

```
pip install -e ".[dev]"
pytest -v
ruff check .
ruff format --check .
mypy src tests
```

(or run the same commands via `docker compose run --rm app sh -c "pip install -e .[dev] && pytest -v"`
if Python 3.12 isn't installed on the host.)

## Notes

- `DATABASE_URL` in `.env` points at `localhost` for running the app directly on the
  host against the dockerised Postgres. When `app` runs *inside* docker-compose,
  `DATABASE_URL` is overridden to point at the `postgres` service hostname instead --
  see `docker-compose.yml`.
- `GET /` is a placeholder service-metadata endpoint, not a health check. A real
  `/health` (DB connectivity + last poll time) lands in a later phase once there's a
  database to check.
