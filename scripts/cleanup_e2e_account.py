"""Deletes the Playwright e2e test account from whatever database DATABASE_URL points at.

apps/web/e2e's specs sign up as E2E_EMAIL (SIGNUP_ALLOWED_EMAILS gates registration, so the
suite reuses one fixed address rather than a fresh one per run). Deleting the user cascades to
its projects, agents, suites and API keys (CASCADE along ownership, ADR 0007), which is
everything a run of the suite creates. playwright.config.ts runs this as globalTeardown; it's
also safe to run by hand: `uv run --env-file .env python scripts/cleanup_e2e_account.py`.
scripts/smoke_prod.py reuses `delete_user` for its throwaway production account.
"""

import asyncio
import os
import selectors
import sys
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentprobe_api.db import make_engine
from agentprobe_api.models import Project, Run, Suite, User

EMAIL = os.environ.get("E2E_EMAIL", "you@example.com")


async def delete_user(database_url: str, email: str) -> uuid.UUID | None:
    """Deletes `email`'s user and everything it owns; returns its id, or None if not found."""
    engine = make_engine(database_url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as db:
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                return None
            # A spec can end mid-run. Cancelling first makes the runner drop its remaining saves
            # (they check the run's status under its row lock); deleting under them deadlocks.
            owned = select(Suite.id).join(Project).where(Project.user_id == user.id)
            await db.execute(
                update(Run)
                .where(Run.suite_id.in_(owned), Run.status.in_(("queued", "running")))
                .values(status="cancelled", finished_at=func.now())
            )
            await db.commit()
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
            return user.id
    finally:
        await engine.dispose()


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    # psycopg's async mode needs the selector loop on Windows (docs/PROGRESS.md known issue).
    if sys.platform == "win32":
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())  # noqa: E731
        return asyncio.run(coro, loop_factory=loop_factory)
    return asyncio.run(coro)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set; nothing to clean up")
        return
    user_id = run_async(delete_user(database_url, EMAIL))
    if user_id is None:
        print(f"no user {EMAIL!r} found")
    else:
        print(f"deleted e2e test user {EMAIL!r} ({user_id})")


if __name__ == "__main__":
    main()
