# Hardened backend image (roadmap F4).
# Multi-stage: deps build in a throwaway layer; runtime is slim, non-root,
# and works with a read-only rootfs (all writes go to /data — see compose).
# At deploy time, pin these base images by digest (docker buildx imagetools
# inspect python:3.11-slim) instead of by tag.

FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim
RUN useradd --system --uid 10001 --create-home att
# /data is the state mountpoint. Compose mounts a volume over it; creating it
# att-owned in the image lets volume-less hosts (e.g. Render's free tier,
# which has no persistent disk) boot the container too — state is ephemeral
# there, so point DATABASE_URL at hosted Postgres for anything that must last.
RUN mkdir -p /data && chown att:att /data
WORKDIR /srv
COPY --from=builder /install /usr/local
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
ENV PYTHONUNBUFFERED=1 \
    # The shipped container is a deploy artifact: arm the production
    # guards (no silent SQLite fallback on a Postgres outage, H1b).
    APP_ENV=production \
    # All mutable state lives on the /data volume (read-only rootfs):
    DATABASE_URL=sqlite:////data/terminal.db \
    RUNS_DIR=/data/runs \
    KILL_SWITCH_FILE=/data/KILL_SWITCH
USER att
EXPOSE 8000
# Schema bootstrap first (H4d): app.core.migrate skips SQLite (init_db owns
# it), stamps legacy create_all Postgres schemas, then alembic-upgrades.
# `exec` hands PID signals to uvicorn so docker stop runs a clean shutdown.
CMD ["sh", "-c", "python -m app.core.migrate && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
