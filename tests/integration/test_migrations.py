from __future__ import annotations

import json
from pathlib import Path

from atlas.persistence.migrations import downgrade_database, upgrade_database
from sqlalchemy import create_engine, inspect, text

M2_REVISION = "9ddd09ccdad2"
M1_REVISION = "467150db4c93"
M0_REVISION = "c4b9a1b5dbf2"


def _columns(engine: object, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _tables(engine: object) -> set[str]:
    return set(inspect(engine).get_table_names())


def _revision(engine: object) -> str:
    with engine.begin() as connection:  # type: ignore[attr-defined]
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar())


def test_migrations_round_trip_and_preserve_earlier_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    upgrade_database(database_url)
    engine = create_engine(database_url, future=True)
    try:
        tables = _tables(engine)
        assert {
            "observations",
            "facts",
            "statements",
            "knowledge",
            "relationships",
            "clocks",
        } <= tables
        turn_columns = _columns(engine, "turns")
        assert {"intent_json", "outcome_json", "attempt_count"} <= turn_columns
        assert "ending_json" in _columns(engine, "campaigns")
        assert _revision(engine) == M2_REVISION

        # An M0-era campaign survives downgrades and re-upgrades.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO campaigns "
                    "(id, title, rules_version, status, state_version, current_time, "
                    "seed, settings_json, created_at, updated_at) "
                    "VALUES ('cmp_migration', 'Migration', '0.1', 'active', 0, 0, 7, "
                    ":settings, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"settings": json.dumps({})},
            )
    finally:
        engine.dispose()

    downgrade_database(database_url, M1_REVISION)
    engine = create_engine(database_url, future=True)
    try:
        tables = _tables(engine)
        assert not ({"facts", "statements", "knowledge", "relationships", "clocks"} & tables)
        assert "ending_json" not in _columns(engine, "campaigns")
        assert _revision(engine) == M1_REVISION
        assert "observations" in tables
    finally:
        engine.dispose()

    downgrade_database(database_url, M0_REVISION)
    engine = create_engine(database_url, future=True)
    try:
        assert "observations" not in _tables(engine)
        turn_columns = _columns(engine, "turns")
        assert not ({"intent_json", "outcome_json", "attempt_count"} & turn_columns)
        assert _revision(engine) == M0_REVISION
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT title FROM campaigns WHERE id = 'cmp_migration'")
                ).scalar()
                == "Migration"
            )
    finally:
        engine.dispose()

    upgrade_database(database_url)
    engine = create_engine(database_url, future=True)
    try:
        assert "observations" in _tables(engine)
        assert {"intent_json", "outcome_json", "attempt_count"} <= _columns(engine, "turns")
        assert "ending_json" in _columns(engine, "campaigns")
        assert _revision(engine) == M2_REVISION
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT title FROM campaigns WHERE id = 'cmp_migration'")
                ).scalar()
                == "Migration"
            )
    finally:
        engine.dispose()
