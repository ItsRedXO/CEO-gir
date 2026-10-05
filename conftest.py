import pytest
import sqlite3
from ceo.db import init_db


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    yield conn
    conn.close()
