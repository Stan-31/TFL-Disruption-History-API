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
USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
