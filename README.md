# TfL Disruption History API

A backend service that answers a question Transport for London's own API can't:
how reliable is a given line, really, over time?

TfL's Unified API only ever reports the current status of a line. There is no
way to ask it how often the Central line was disrupted last month, how long an
incident lasted, or what a line's actual uptime looks like over a given week.
This service closes that gap. It polls TfL's live status feed on a fixed
schedule, builds a continuous historical record from every observation, and
exposes that record through a documented read API.

**Live deployment:** https://tfl-disruption-history-api-production.up.railway.app
(`/` and `/health` are open; the data endpoints require an API key, see
[Authentication](#authentication))

## Overview

- Polls the London Underground, Overground, DLR, Elizabeth line, and all
  ~700 London bus routes every 60 seconds.
- Stores every status change as a discrete time period, not a raw log of
  polls, so a line that holds "Good Service" for six hours is one row, not
  360 of them.
- Serves current status, full history, and computed uptime statistics through
  a REST API, with pagination, time-window filtering, and mode filtering.
- Recovers from upstream failures automatically: a flaky TfL API triggers
  exponential backoff instead of hammering the endpoint or crashing the
  service.
- Runs as a single containerised process with automated database migrations,
  a full test suite against a real database (not mocks), and CI on every
  push.

## Why this exists

Transport apps and commute-planning tools all consume TfL's current-status
feed, but none of them can tell you whether a line is reliable. "Minor Delays"
right now says nothing about whether that line has been disrupted every
weekday this month. Answering that requires storing history somewhere, and
TfL doesn't do it. This service does, and turns it into a queryable API rather
than a one-off script or a spreadsheet.

## Architecture

```
┌─────────────┐     poll every 60s      ┌──────────────────┐
│  TfL Line    │ ───────────────────▶   │   Poller          │
│  Status API  │                        │  (async, with     │
└─────────────┘                        │  exponential      │
                                        │  backoff)         │
                                        └─────────┬─────────┘
                                                   │ writes
                                                   ▼
                                        ┌──────────────────┐
                                        │   PostgreSQL      │
                                        │  line_status_     │
                                        │  periods          │
                                        └─────────┬─────────┘
                                                   │ reads
                                                   ▼
                                        ┌──────────────────┐
       client ◀────────────────────────│    FastAPI        │
                     JSON               │   read API        │
                                        └──────────────────┘
```

The poller and the API run in the same process (one FastAPI app with a
background asyncio task), backed by one Postgres database. There's no queue,
cache, or second service: at this scale, that would be complexity the problem
doesn't need.

## API reference

All responses are JSON. Timestamps are ISO 8601, UTC.

### `GET /lines`

Every currently-tracked line and its current status.

Query params: `mode` (optional) — restrict to one mode, e.g. `bus` or `tube`.
Useful since bus alone is several hundred routes.

```
curl https://tfl-disruption-history-api-production.up.railway.app/lines?mode=tube \
  -H "X-API-Key: <your key>"
```

```json
[
  {
    "line_id": "central",
    "line_name": "Central",
    "mode_name": "tube",
    "status_severity": 9,
    "status_severity_description": "Minor Delays",
    "reason": "Central Line: Minor delays between White City and Ealing Broadway...",
    "started_at": "2026-07-22T11:01:57Z",
    "last_seen_at": "2026-07-22T20:22:53Z"
  }
]
```

### `GET /disruptions`

Every line currently in a state other than "Good Service", across all modes.
Same `mode` filter as above. This is the "what's actually broken right now"
view, without checking each line one at a time.

### `GET /lines/{line_id}/history`

Paginated status history for one line, most recent period first.

Query params: `since` (ISO timestamp), `limit` (default 50, max 500),
`offset`. Returns `404` for an unrecognised `line_id`.

```json
{
  "line_id": "central",
  "line_name": "Central",
  "mode_name": "tube",
  "total": 42,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 1381,
      "status_severity": 9,
      "status_severity_description": "Minor Delays",
      "reason": "Central Line: Minor delays...",
      "started_at": "2026-07-22T11:01:57Z",
      "ended_at": null,
      "last_seen_at": "2026-07-22T20:22:53Z"
    }
  ]
}
```

### `GET /lines/{line_id}/stats`

Disruption statistics for one line over a time window.

Query params: `since`, `until` (both optional; default to the full recorded
history through now). Returns `404` for an unrecognised `line_id`.

```json
{
  "line_id": "central",
  "line_name": "Central",
  "mode_name": "tube",
  "window_start": "2026-07-22T11:01:57Z",
  "window_end": "2026-07-22T20:22:53Z",
  "total_seconds": 33656,
  "disrupted_seconds": 33656,
  "uptime_percentage": 0.0,
  "disruption_count": 1
}
```

### `GET /health`

Database connectivity and poller freshness, for uptime monitoring. Returns
`"status": "degraded"` if the most recent successful poll is older than three
times the poll interval (or there's never been one), and a `503` if the
database itself is unreachable. Never gated by an API key.

### `GET /`

Service metadata only (name, status, environment). Not a substitute for
`/health`.

## Authentication

Every endpoint above except `/` and `/health` can require a matching
`X-API-Key` header. It's opt-in at the code level: if the `API_KEY`
environment variable isn't set, those endpoints stay open, which is what
local development and CI both do. The production deployment has a key set,
because a public, unauthenticated read API on a metered hosting plan is an
easy way to run up a bill. `/` and `/health` are never gated, so uptime
monitoring and load balancer health checks keep working regardless.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI |
| Database | PostgreSQL |
| ORM / migrations | SQLAlchemy 2.0, Alembic |
| HTTP client | httpx (async) |
| Testing | pytest, against a real Postgres instance |
| Linting / types | ruff, mypy (strict mode) |
| Containerisation | Docker, docker-compose |
| CI | GitHub Actions |
| Hosting | Railway |

## Getting started

Requires Docker.

```bash
git clone https://github.com/Stan-31/TFL-Disruption-History-API.git
cd TFL-Disruption-History-API
cp .env.example .env
```

Edit `.env` and set `TFL_APP_KEY` to a real key from the
[TfL API Portal](https://api-portal.tfl.gov.uk/) (free to register). A
placeholder value still lets the app start; the poller will just log failed
polls until a real key is set.

```bash
docker compose up --build
```

Visit `http://localhost:8000/`. You should see:

```json
{"service": "tfl-disruption-history-api", "status": "ok", "environment": "local"}
```

`docker compose up` runs pending Alembic migrations automatically before the
app starts. Once it's been running with a real `TFL_APP_KEY` for a minute or
two, you can inspect accumulated history directly:

```bash
docker compose exec postgres psql -U tfl -d tfl_disruption_history \
  -c "select line_id, status_severity_description, started_at, last_seen_at, ended_at from line_status_periods order by line_id;"
```

## Running the tests

Requires a running Postgres with migrations applied (the docker-compose one
works fine):

```bash
pip install -e ".[dev]"
alembic upgrade head
pytest -v
ruff check .
ruff format --check .
mypy src tests
```

If Python 3.12 isn't installed on the host, the same commands run inside the
container:

```bash
docker compose run --rm app sh -c "pip install -e .[dev] && alembic upgrade head && pytest -v"
```

Each test runs inside a database transaction that's rolled back afterward, so
the suite is safe to run repeatedly against the same database without
accumulating test data.

## Deployment

The production instance runs on Railway: one service for the app (built
straight from the `Dockerfile`, no buildpack) and one for Postgres, in the
same project. The app service needs these variables set, none of which carry
over from `.env` automatically:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Must use the `postgresql+psycopg://` scheme (the psycopg 3 driver), not plain `postgresql://` |
| `TFL_APP_KEY` | A real TfL Unified API key |
| `ENVIRONMENT` | Set to `production` |
| `API_KEY` | Enables auth on the read endpoints (see [Authentication](#authentication)) |

`docker compose up` and CI both run migrations automatically; production does
the same via the container's start command (`alembic upgrade head` before
`uvicorn` starts).

## Design notes

A few decisions that aren't obvious from the code alone:

- **History is stored as periods, not polls.** Each row in
  `line_status_periods` represents a continuous stretch of time a line held
  one status. A new poll either extends the currently open period (if the
  status hasn't changed) or closes it and opens a new one. This keeps the
  table small and makes uptime calculations a straightforward interval sum
  instead of a scan over every poll ever recorded.
- **Backoff only kicks in after a second consecutive failure.** A single
  transient failure doesn't change the poll cadence at all; from the second
  failure onward the delay doubles, capped at 30 minutes, so a sustained
  outage on TfL's side doesn't turn into a retry storm.
- **"Disrupted" means anything other than TfL's own "Good Service" code.**
  That's the one place the severity scale's meaning is hardcoded, deliberately
  and narrowly, because a disruption-stats endpoint has to draw that line
  somewhere and TfL's own definition is the least arbitrary one available.
- **Bus support needed its own filter.** Bus alone contributes several
  hundred routes to `/lines` and `/disruptions`, most of them reporting "Good
  Service" almost all the time. Without the `mode` query parameter, bus data
  would dominate both endpoints and bury the much smaller, more meaningful
  rail dataset.
- **Tests run against a real Postgres instance, never mocks.** Mocking the
  database would mean the tests couldn't catch a broken migration, an
  incorrect constraint, or a query that's only wrong under real transactional
  behaviour. The tradeoff is that the suite needs Postgres available to run at
  all, which is why CI provisions one as a service container.

## License

MIT. See [LICENSE](LICENSE).
