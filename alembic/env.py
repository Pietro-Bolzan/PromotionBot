"""Alembic environment.

The database URL is read from the application settings (DATABASE_URL in .env or
in the process environment), never from alembic.ini, so that migrations and the
running application can never disagree about which database they target.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# alembic.ini sets `prepend_sys_path = .`, which puts the project root on
# sys.path and makes the `app` package importable from here.
from app.core.config import settings
from app.db.database import Base

# Imported for its side effect: it registers the Promotion model on
# Base.metadata, which is what `alembic revision --autogenerate` compares
# against the live database. Without it, autogenerate would see no tables.
from app.models import promotions  # noqa: F401

config = context.config

# `disable_existing_loggers=False` keeps loggers configured by the application
# alive, which matters once migrations run at application startup.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migrations as SQL to stdout, without connecting to a database."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection.

    The engine is built from settings.database_url instead of
    engine_from_config() so the URL is never passed through ConfigParser, whose
    pyformat interpolation would reject a percent-encoded password.
    """
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
