# TfL Disruption History API

TfL's Unified API only exposes *current* line status -- there's no history endpoint.
This service polls it on a schedule, persists every observation, and exposes the
historical record TfL doesn't: how often each line is disrupted, when, for how long,
and with what severity.

Status: **Phase 11** -- database schema, TfL client, an in-process poller
(default: every 60s, see `TFL_POLL_INTERVAL_SECONDS`, with exponential backoff
up to 30 minutes on repeated failures) covering tube, overground, DLR,
Elizabeth line, and bus, and a read API over the accumulated history:

- `GET /lines` -- every polled line with its current status; optional `mode`
  query param (e.g. `?mode=bus`) to filter to one mode, since bus alone is
  hundreds of routes
- `GET /disruptions` -- currently polled lines that aren't in "Good Service",
  across every mode -- a "what's broken right now" view without checking each
  line individually; also supports `?mode=`
- `GET /lines/{line_id}/history` -- paginated status history for one line, most
  recent first (`limit`/`offset`/`since` query params), `404` for an unknown
  `line_id`
- `GET /lines/{line_id}/stats` -- disruption stats for one line over a window
  (`since`/`until` query params, defaults to full recorded history through
  now): total/disrupted seconds, uptime %, disruption count. `404` for an
  unknown `line_id`
- `GET /health` -- DB connectivity and last successful poll time; `status` is
  `"degraded"` if the last poll is more than 3x `TFL_POLL_INTERVAL_SECONDS`
  old (or there's never been one), `503` if the database itself is unreachable

If `API_KEY` is set, the four data endpoints above (everything except `/` and
`/health`) require a matching `X-API-Key` header, `401` otherwise. Unset by
default -- opt-in, since it's not needed for local dev.

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
- Deployed on Railway (project `merry-caring`); the service needs its own
  `DATABASE_URL` (pointing at the project's Postgres plugin, with the
  `+psycopg` dialect SQLAlchemy expects), `TFL_APP_KEY`, `ENVIRONMENT=production`,
  and `API_KEY` set as Railway variables -- none of these carry over from
  `.env` automatically. Live at
  https://tfl-disruption-history-api-production.up.railway.app, polling with a
  real TfL app key; the data endpoints there require the production `API_KEY`
  as an `X-API-Key` header.
- Bus is included in the default `TFL_MODES`. Most bus routes report "Good
  Service" almost all the time (real bus disruptions mostly surface via
  stop/road disruptions rather than line status), so it adds a lot of rows for
  comparatively little signal -- the `mode` filter on `/lines` and
  `/disruptions` exists mainly to keep bus's few hundred routes from drowning
  out everything else. The TfL client's request timeout is 30s (up from 10s)
  to give the much larger bus response room.
