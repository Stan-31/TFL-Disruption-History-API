# TfL Disruption History API

TfL's Unified API only exposes *current* line status -- there's no history endpoint.
This service polls it on a schedule, persists every observation, and exposes the
historical record TfL doesn't: how often each line is disrupted, when, for how long,
and with what severity.

Status: **Phase 4** -- database schema, TfL client, an in-process poller
(default: every 60s, see `TFL_POLL_INTERVAL_SECONDS`), and a read API over the
accumulated history:

- `GET /lines` -- every polled line with its current status
- `GET /lines/{line_id}/history` -- paginated status history for one line, most
  recent first (`limit`/`offset`/`since` query params), `404` for an unknown
  `line_id`
- `GET /health` -- DB connectivity and last successful poll time; `status` is
  `"degraded"` if the last poll is more than 3x `TFL_POLL_INTERVAL_SECONDS`
  old (or there's never been one), `503` if the database itself is unreachable

## Stack

Python 3.12, FastAPI, PostgreSQL (SQLAlchemy 2.x + Alembic), pytest, Docker /
docker-compose, GitHub Actions.

## Running locally

```
cp .env.example .env
# edit .env and set TFL_APP_KEY -- a real key (register at
# https://api-portal.tfl.gov.uk/) is needed for the poller to actually fetch data;
# a placeholder still lets the app start, it'll just log failed polls
docker compose up --build
```

Then visit http://localhost:8000/ -- you should see:

```json
{"service": "tfl-disruption-history-api", "status": "ok", "environment": "local"}
```

`docker compose up` runs pending Alembic migrations automatically before starting
the app. With a real `TFL_APP_KEY`, check accumulated history directly:

```
docker compose exec postgres psql -U tfl -d tfl_disruption_history \
  -c "select line_id, status_severity_description, started_at, last_seen_at, ended_at from line_status_periods order by line_id;"
```

## Tests

Requires a running Postgres with migrations applied (the docker-compose one works):

```
pip install -e ".[dev]"
alembic upgrade head
pytest -v
ruff check .
ruff format --check .
mypy src tests
```

(or run the same commands via `docker compose run --rm app sh -c "pip install -e .[dev] && alembic upgrade head && pytest -v"`
if Python 3.12 isn't installed on the host.) Tests run inside a transaction that's
rolled back afterwards, so they're safe to run repeatedly against the same database
without leaving data behind.

## Notes

- `DATABASE_URL` in `.env` points at `localhost` for running the app directly on the
  host against the dockerised Postgres. When `app` runs *inside* docker-compose,
  `DATABASE_URL` is overridden to point at the `postgres` service hostname instead --
  see `docker-compose.yml`.
- `GET /` is service metadata, not a health check -- use `GET /health` for that.
