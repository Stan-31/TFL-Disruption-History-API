# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY src ./src

# Trust any locally-provided CA certs (e.g. corporate/network TLS-inspection
# proxies) so pip can reach PyPI. docker/certs/ is empty and gitignored by
# default, so this is a no-op on machines without such a proxy (e.g. CI).
RUN --mount=type=bind,source=docker/certs,target=/tmp/certs \
    cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ 2>/dev/null || true; \
    update-ca-certificates

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations

# Same local-CA trust as the builder stage (see above) -- lets `docker compose
# run app pip install ...` work for ad hoc dev tooling (e.g. installing `[dev]`
# extras to run tests/lint) on a TLS-inspecting network. No-op elsewhere.
RUN --mount=type=bind,source=docker/certs,target=/tmp/certs \
    cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ 2>/dev/null || true; \
    update-ca-certificates

# httpx (used by tfl_client.py) bundles its own certifi CA list by default and
# ignores the OS trust store update above -- point it at the OS bundle instead
# so it also trusts any locally-provided CA certs. Harmless when none exist.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

USER appuser
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
