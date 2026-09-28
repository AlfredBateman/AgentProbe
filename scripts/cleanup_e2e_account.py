"""Deletes the Playwright e2e test account from whatever database DATABASE_URL points at.

apps/web/e2e's specs sign up as E2E_EMAIL (SIGNUP_ALLOWED_EMAILS gates registration, so the
suite reuses one fixed address rather than a fresh one per run). Deleting the user cascades to
its projects, agents, suites and API keys (CASCADE along ownership, ADR 0007), which is
everything a run of the suite creates. playwright.config.ts runs this as globalTeardown; it's
also safe to run by hand: `uv run --env-file .env python scripts/cleanup_e2e_account.py`.
"""

import asyncio
import os
import selectors
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentprobe_api.db import make_engine
from agentprobe_api.models import User

EMAIL = os.environ.get("E2E_EMAIL", "you@example.com")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set; nothing to clean up")
        return
    engine = make_engine(database_url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as db:
            user = await db.scalar(select(User).where(User.email == EMAIL))
            if user is None:
                print(f"no user {EMAIL!r} found")
                return
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
            print(f"deleted e2e test user {EMAIL!r} ({user.id})")
    finally:
        await engine.dispose()


def run() -> None:
    # psycopg's async mode needs the selector loop on Windows (docs/PROGRESS.md known issue).
    if sys.platform == "win32":
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())  # noqa: E731
        asyncio.run(main(), loop_factory=loop_factory)
    else:
        asyncio.run(main())


if __name__ == "__main__":
    run()
