"""Proves the root conftest refuses integration tests unless the DB env is safe."""

from collections.abc import Callable
from pathlib import Path

import pytest

ROOT_CONFTEST = Path(__file__).parents[3] / "conftest.py"
TEST_DB = "postgresql://u:p@ep-test.neon.tech/app"
MAIN_DB = "postgresql://u:p@ep-main.neon.tech/app"
Runner = Callable[..., pytest.RunResult]


@pytest.fixture
def run_guarded(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Runner:
    pytester.makeconftest(ROOT_CONFTEST.read_text())
    pytester.makeini(
        "[pytest]\n"
        "asyncio_default_fixture_loop_scope = function\n"
        "markers =\n    integration: db\n    live: llm\n"
    )
    pytester.makepyfile("import pytest\n\n@pytest.mark.integration\ndef test_db():\n    pass\n")
    for name in ("TEST_DATABASE_URL", "DATABASE_URL", "ALLOW_DB_TESTS"):
        monkeypatch.delenv(name, raising=False)

    def run(**env: str) -> pytest.RunResult:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return pytester.runpytest("-m", "integration", "-p", "no:cacheprovider")

    return run


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({"DATABASE_URL": MAIN_DB, "ALLOW_DB_TESTS": "1"}, "TEST_DATABASE_URL is not set"),
        (
            {"TEST_DATABASE_URL": MAIN_DB, "DATABASE_URL": MAIN_DB, "ALLOW_DB_TESTS": "1"},
            "different database",
        ),
        (
            {
                "TEST_DATABASE_URL": MAIN_DB.replace("postgresql://", "postgresql+psycopg://")
                + "?sslmode=require",
                "DATABASE_URL": MAIN_DB,
                "ALLOW_DB_TESTS": "1",
            },
            "different database",
        ),
        ({"TEST_DATABASE_URL": TEST_DB, "DATABASE_URL": MAIN_DB}, "ALLOW_DB_TESTS=1 is not set"),
        (
            {"TEST_DATABASE_URL": TEST_DB, "DATABASE_URL": MAIN_DB, "ALLOW_DB_TESTS": "0"},
            "ALLOW_DB_TESTS=1 is not set",
        ),
    ],
    ids=["no-test-url", "same-url", "same-db-other-spelling", "allow-unset", "allow-zero"],
)
def test_guard_refuses(run_guarded: Runner, env: dict[str, str], reason: str) -> None:
    result = run_guarded(**env)
    assert result.ret == 2
    result.stdout.fnmatch_lines([f"*Refusing to run DB tests: *{reason}*"])


def test_guard_allows_safe_env(run_guarded: Runner) -> None:
    result = run_guarded(TEST_DATABASE_URL=TEST_DB, DATABASE_URL=MAIN_DB, ALLOW_DB_TESTS="1")
    assert result.ret == 0
    result.assert_outcomes(passed=1)
