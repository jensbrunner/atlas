"""Programmatic Alembic migration runner (also used by tests)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def upgrade_database(database_url: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    # Alembic Config uses ConfigParser interpolation; percent signs must be escaped.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")
