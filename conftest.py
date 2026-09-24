"""Refuses to run tests that touch real infrastructure unless explicitly allowed."""

import asyncio
import os
import sys
from urllib.parse import urlsplit

import pytest

pytest_plugins = ["pytester"]


def _db_target(url: str) -> tuple[str, int, str]:
    # Compare the database a URL points at, not its spelling: postgresql:// and
    # postgresql+psycopg:// (or reordered query params) reach the same database.
    parts = urlsplit(url)
    return ((parts.hostname or "").lower(), parts.port or 5432, parts.path.strip("/"))


def _db_refusal() -> str | None:
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    if not test_url:
        return "TEST_DATABASE_URL is not set"
    main_url = os.environ.get("DATABASE_URL", "")
    if main_url and _db_target(test_url) == _db_target(main_url):
        return "TEST_DATABASE_URL must point at a different database than DATABASE_URL"
    if os.environ.get("ALLOW_DB_TESTS") != "1":
        return "ALLOW_DB_TESTS=1 is not set"
    return None


@pytest.hookimpl(trylast=True)  # after -m deselection
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    markers = {m.name for item in items for m in item.iter_markers()}
    if "integration" in markers and (reason := _db_refusal()):
        pytest.exit(f"Refusing to run DB tests: {reason}.", returncode=2)
    if "live" in markers and os.environ.get("RUN_LIVE") != "1":
        pytest.exit("Refusing to run live LLM tests: RUN_LIVE=1 is not set.", returncode=2)


if sys.platform == "win32":
    # psycopg's async mode can't run on Windows' default ProactorEventLoop.
    def pytest_asyncio_loop_factories(
        config: pytest.Config, item: pytest.Item
    ) -> dict[str, type[asyncio.AbstractEventLoop]]:
        return {"selector": asyncio.SelectorEventLoop}
