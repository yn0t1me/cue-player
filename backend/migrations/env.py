from pathlib import Path

from alembic import context
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.db.base import Base
from app.db import models  # noqa: F401 — register all five tables
from app.db.session import create_db_engine

settings = Settings()
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={'paramstyle': 'named'}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Migrations own database creation, including a custom database parent path.
    Path(make_url(settings.database_url).database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
