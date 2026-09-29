"""Programmatic Alembic runner. Migrations are the only way the schema changes."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _config(sync_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


def upgrade(sync_url: str, revision: str = "head") -> None:
    command.upgrade(_config(sync_url), revision)


def downgrade(sync_url: str, revision: str) -> None:
    command.downgrade(_config(sync_url), revision)


def current_revision(sync_url: str) -> str | None:
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def head_revision(sync_url: str) -> str | None:
    return ScriptDirectory.from_config(_config(sync_url)).get_current_head()


def autogenerate(sync_url: str, message: str) -> None:
    command.revision(_config(sync_url), message=message, autogenerate=True)
