from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A Session bound to a transaction that's rolled back after the test.

    Assumes `alembic upgrade head` has already been run against DATABASE_URL
    (a CI step, and a documented prerequisite for running pytest locally) --
    this validates tests against the migration-created schema rather than a
    `Base.metadata.create_all()` shortcut that could silently drift from it.
    """
    engine = create_engine(str(get_settings().database_url))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
