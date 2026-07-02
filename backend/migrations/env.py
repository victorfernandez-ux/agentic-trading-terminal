"""Alembic environment.

By default migrations reuse the application's engine (app.core.db.engine) so
they honour the same DATABASE_URL-with-SQLite-fallback behaviour as the running
app. Tests/CI can override by setting `sqlalchemy.url` on the Alembic config.
Targets Base.metadata so `alembic revision --autogenerate` stays in sync.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app.core.db import Base

config = context.config
target_metadata = Base.metadata


def _connectable():
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return create_engine(url)
    from app.core.db import engine
    return engine


def run_migrations_offline() -> None:
    context.configure(
        url=str(_connectable().url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite-safe ALTERs
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with _connectable().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-safe ALTERs
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
