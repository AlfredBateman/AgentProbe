import os

import psycopg
import pytest


@pytest.mark.integration
def test_test_database_is_reachable() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
