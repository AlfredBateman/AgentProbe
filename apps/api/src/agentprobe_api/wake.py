"""Waking an agent host that sleeps when idle (ADR 0036).

Free web services sleep after about 15 idle minutes and take about a minute to wake. The demo
agents run on one, so a run's first attempts would hit the adapter's 30 s timeout. A run or a
connection test against a WAKE_TARGET_HOSTS host first polls that host's GET /health until it
answers, through the same SSRF guard as every agent call. Best effort: when it never answers,
the real call that follows reports why.
"""

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from agentprobe_api.settings import Settings
from agentprobe_core.adapters import TargetPolicy, guarded_client
from agentprobe_core.adapters.ssrf import TargetBlocked

log = logging.getLogger("agentprobe.wake")

WAKE_BUDGET_S = 120.0
RETRY_S = 5.0


async def wake_target(
    config: dict[str, Any],
    settings: Settings,
    *,
    budget_s: float = WAKE_BUDGET_S,
    client: httpx.AsyncClient | None = None,  # tests; otherwise a guarded client
) -> None:
    url = urlsplit(str(config.get("url", "")))
    if not url.hostname or url.hostname.lower() not in settings.wake_hosts:
        return
    health = f"{url.scheme}://{url.netloc}/health"
    deadline = time.monotonic() + budget_s
    http = client or guarded_client(
        policy=TargetPolicy.from_env(),
        allow_private=bool(config.get("allow_private")),
        timeout_s=budget_s,
    )
    async with http:
        while True:
            try:
                # One request can take most of a minute: the platform holds it while it wakes.
                response = await http.get(health, timeout=deadline - time.monotonic())
                if response.status_code < 500:
                    return
            except TargetBlocked:
                return  # the real call reports the policy error
            except httpx.HTTPError:
                pass
            if time.monotonic() + RETRY_S >= deadline:
                log.warning("agent host did not wake", extra={"host": url.hostname})
                return
            await asyncio.sleep(RETRY_S)
