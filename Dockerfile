# Build Python wheels in a compiler-equipped stage.
# pyswisseph 2.10.3.2 does not publish a Linux CPython 3.12 wheel,
# so pip must compile its C extension.
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip wheel setuptools \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# Small runtime image: compiler toolchain stays behind in the builder.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5055 \
    LUNELLE_DB_PATH=/data/period_tracker.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY --from=builder /wheels /wheels

RUN python -m pip install --no-cache-dir --no-index \
      --find-links=/wheels \
      -r requirements.txt \
    && rm -rf /wheels

COPY . .

RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data

VOLUME ["/data"]
EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5055/login >/dev/null || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
