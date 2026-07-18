"""Deploy-time schema bootstrap — run before uvicorn (Docker CMD).

Rules (H4d, amended after review):
- SQLite: do nothing here. init_db's create_all + additive upgrader owns
  the zero-setup path, and running Alembic 0001 against an existing
  create_all-made file would fail on the first CREATE TABLE.
- Anything else (Postgres): Alembic is the source of truth. A legacy
  database that was created by the old create_all path (has `orders` but
  no `alembic_version`) is adopted via `alembic stamp head` first, so
  existing volumes upgrade instead of crash-looping; then `upgrade head`
  applies anything newer.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect

from app.config import settings

log = logging.getLogger("migrate")


def main() -> None:
    url = settings.database_url
    if url.startswith("sqlite"):
        log.info("sqlite database — schema handled by init_db, skipping alembic")
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    eng = create_engine(url)
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    if "orders" in tables and "alembic_version" not in tables:
        log.warning("legacy create_all schema detected — stamping alembic head")
        command.stamp(cfg, "head")
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
