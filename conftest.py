"""Refuses to run tests that touch real infrastructure unless explicitly allowed."""

import os

import pytest


def _db_refusal() -> str | None:
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    if not test_url:
        return "TEST_DATABASE_URL is not set"
    if test_url == os.environ.get("DATABASE_URL", ""):
        return "TEST_DATABASE_URL must differ from DATABASE_URL"
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
