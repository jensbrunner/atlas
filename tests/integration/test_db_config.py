from __future__ import annotations

import pytest
from atlas.config import Settings
from atlas.persistence.db import BUSY_TIMEOUT_MS
from sqlalchemy import Engine


def test_sqlite_pragmas_are_applied(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == BUSY_TIMEOUT_MS
        assert str(connection.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO entities "
                    "(id, campaign_id, kind, slug, display_name, static_json) "
                    "VALUES ('ent_bad', 'cmp_missing', 'npc', 'bad', 'Bad', '{}')"
                )
            )


def test_unavailable_modes_fail_loudly() -> None:
    with pytest.raises(ValueError, match="not available in M0"):
        Settings(mode="balanced").assert_mode_is_configured()
    Settings(mode="offline_test").assert_mode_is_configured()
