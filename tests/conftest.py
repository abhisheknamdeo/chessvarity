import os
import uuid
from urllib.parse import quote

import pytest

from chesscoach.engine import DEFAULT_ENGINE, Engine


@pytest.fixture(autouse=True)
def postgres_schema(monkeypatch):
    """With TEST_DATABASE_URL set, every app in the test uses PostgreSQL, in a fresh schema of its own."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        yield
        return
    import psycopg

    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in url else "?"
    monkeypatch.setenv("DATABASE_URL", f"{url}{sep}options={quote(f'-csearch_path={schema}')}")
    yield
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(scope="session")
def engine():
    if not DEFAULT_ENGINE.exists():
        pytest.skip("Stockfish binary not available")
    with Engine(depth=10) as eng:
        yield eng
