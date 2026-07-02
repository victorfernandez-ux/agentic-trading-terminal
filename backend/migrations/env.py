"""Alembic environment. Targets the app's models metadata.

URL resolution order: sqlalchemy.url from the config (set programmatically
or in alembic.ini) -> the app engine (settings.DATABASE_URL with its
SQLite fallback). Keeping resolution here means `alembic upgrade head`
works against exactly the database the app itself would use.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core import db

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = db.Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or str(db.engine.url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    override = config.get_main_option("sqlalchemy.url")
    engine = create_engine(override) if override else db.engine
    with engine.connect() as connection:
        context.configure(connection=connection,
                          target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
