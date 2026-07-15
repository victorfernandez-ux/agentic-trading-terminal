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
WORKDIR /srv
COPY --from=builder /install /usr/local
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
ENV PYTHONUNBUFFERED=1 \
    # All mutable state lives on the /data volume (read-only rootfs):
    DATABASE_URL=sqlite:////data/terminal.db \
    RUNS_DIR=/data/runs \
    KILL_SWITCH_FILE=/data/KILL_SWITCH
USER att
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
