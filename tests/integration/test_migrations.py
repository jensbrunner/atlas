from __future__ import annotations

import json
from pathlib import Path

from atlas.persistence.migrations import downgrade_database, upgrade_database
from sqlalchemy import create_engine, inspect, text

M1_REVISION = "467150db4c93"
M0_REVISION = "c4b9a1b5dbf2"


def _columns(engine: object, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _tables(engine: object) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_m1_migration_round_trips_and_preserves_m0_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    upgrade_database(database_url)
    engine = create_engine(database_url, future=True)
    try:
        assert "observations" in _tables(engine)
        turn_columns = _columns(engine, "turns")
        assert {"intent_json", "outcome_json", "attempt_count"} <= turn_columns
        observation_columns = _columns(engine, "observations")
        assert {
            "id",
            "campaign_id",
            "turn_id",
            "seq",
            "text",
            "kind",
            "subject_ids_json",
            "visibility",
            "occurred_at_world",
            "created_at",
        } <= observation_columns

        with engine.begin() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert revision == M1_REVISION

        # An M0-era campaign survives the downgrade and re-upgrade.
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

    downgrade_database(database_url, M0_REVISION)
    engine = create_engine(database_url, future=True)
    try:
        assert "observations" not in _tables(engine)
        turn_columns = _columns(engine, "turns")
        assert not ({"intent_json", "outcome_json", "attempt_count"} & turn_columns)
        with engine.begin() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == M0_REVISION
            )
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
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT title FROM campaigns WHERE id = 'cmp_migration'")
                ).scalar()
                == "Migration"
            )
    finally:
        engine.dispose()
