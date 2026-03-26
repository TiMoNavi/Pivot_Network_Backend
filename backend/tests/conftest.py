import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

TEST_DATABASE_PATH = Path(__file__).resolve().parent / "test_backend.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"

from app.main import app
from app.core.db import engine
from app.models import Base


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    engine.dispose()
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table_name in inspect(connection).get_table_names():
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
        Base.metadata.create_all(bind=connection)
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    engine.dispose()
    yield


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
