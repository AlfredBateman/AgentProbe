"""Resets the Neon test database to empty: every app table truncated, sequences restarted.

apps/web/e2e's Playwright `globalSetup` runs this before every invocation, so each of the "3
consecutive passes" a stable e2e suite needs starts from a clean database instead of relying
on a single reserved email and per-spec cleanup (which doesn't scale to a whole journey test
that creates several projects, agents and suites).

Always targets TEST_DATABASE_URL, never DATABASE_URL, and refuses unless the same guard
conftest.py uses for DB tests holds: TEST_DATABASE_URL is set, differs from DATABASE_URL (when
both are given), and ALLOW_DB_TESTS=1. That way a misconfigured environment can't truncate a
real database — only ever the one this repo's own tests are already allowed to touch.
"""

import asyncio
import os
import selectors
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentprobe_api.db import make_engine
from agentprobe_api.models import Base


def _db_target(url: str) -> tuple[str, int, str]:
    parts = urlsplit(url)
    return ((parts.hostname or "").lower(), parts.port or 5432, parts.path.strip("/"))


def _refusal() -> str | None:
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    if not test_url:
        return "TEST_DATABASE_URL is not set"
    main_url = os.environ.get("DATABASE_URL", "")
    if main_url and _db_target(test_url) == _db_target(main_url):
        return "TEST_DATABASE_URL must point at a different database than DATABASE_URL"
    if os.environ.get("ALLOW_DB_TESTS") != "1":
        return "ALLOW_DB_TESTS=1 is not set"
    return None


async def main() -> None:
    reason = _refusal()
    if reason:
        print(f"Refusing to reset: {reason}.", file=sys.stderr)
        raise SystemExit(2)
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    try:
        tables = [t.name for t in Base.metadata.sorted_tables]
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as db:
            if tables:
                names = ", ".join(tables)
                await db.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
            await db.commit()
        print(f"reset {len(tables)} tables in the test database")
    finally:
        await engine.dispose()


def run() -> None:
    # psycopg's async mode needs the selector loop on Windows.
    if sys.platform == "win32":
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())  # noqa: E731
        asyncio.run(main(), loop_factory=loop_factory)
    else:
        asyncio.run(main())


if __name__ == "__main__":
    run()
