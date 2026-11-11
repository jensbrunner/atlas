from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from atlas.persistence.db import create_db_engine, create_session_factory
from atlas.persistence.migrations import upgrade_database
from atlas.seed.broken_span import SeedResult, seed_broken_span
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'atlas_test.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    upgrade_database(database_url)
    engine = create_db_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_result(session: Session) -> SeedResult:
    result = seed_broken_span(session)
    session.commit()
    return result
