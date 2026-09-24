from typing import Any

import pytest

from adapterfakes import HOST, PUBLIC_IP, FakeBackend, FakeClock, MakeAdapter, static_resolver
from agentprobe_core.adapters import HttpAdapter, HttpAdapterConfig, TargetPolicy
from agentprobe_core.adapters.ssrf import Resolver


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_adapter(clock: FakeClock) -> MakeAdapter:
    def make(
        backend: FakeBackend,
        *,
        resolver: Resolver | None = None,
        policy: TargetPolicy | None = None,
        secret_headers: Any = None,
        **config: Any,
    ) -> HttpAdapter:
        cfg = HttpAdapterConfig.model_validate({"url": f"https://{HOST}/chat", **config})
        return HttpAdapter(
            cfg,
            secret_headers=secret_headers,
            policy=policy or TargetPolicy(),
            resolver=resolver or static_resolver({HOST: [PUBLIC_IP]}),
            network_backend=backend,
            clock=clock,
        )

    return make
