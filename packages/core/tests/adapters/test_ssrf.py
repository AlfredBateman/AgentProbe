"""SSRF guard: every blocked address class, the private-target opt-in, pinning the validated
address (DNS rebinding), redirects, and proxies from the environment.
"""

import ipaddress
import logging

import pytest
from pydantic import SecretStr, ValidationError

from adapterfakes import (
    HOST,
    OTHER_PUBLIC_IP,
    PUBLIC_IP,
    FakeBackend,
    MakeAdapter,
    http_response,
    static_resolver,
)
from agentprobe_core.adapters import HttpAdapterConfig, TargetPolicy
from agentprobe_core.adapters.ssrf import AddressClass, classify

BLOCKED_CLASSES = {
    "unspecified": ["0.0.0.0", "0.1.2.3", "::"],  # noqa: S104
    "link-local": ["169.254.0.1", "169.254.254.254", "fe80::1"],
    "aws/gcp/azure metadata": ["169.254.169.254"],
    "ecs/eks metadata": ["169.254.170.2", "169.254.170.23"],
    "alibaba metadata (inside CGNAT)": ["100.100.100.200"],
    "aws ipv6 metadata (inside ULA)": ["fd00:ec2::254", "fd00:ec2::23"],
    "azure wireserver (public range)": ["168.63.129.16"],
    "ipv4-mapped": ["::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:8.8.8.8"],
    "ipv4-compatible": ["::7f00:1", "::a9fe:a9fe"],
    "nat64 of metadata": ["64:ff9b::a9fe:a9fe"],
    "local-use nat64": ["64:ff9b:1::7f00:1"],
    "6to4": ["2002:7f00:1::1", "2002:a9fe:a9fe::1"],
    "teredo": ["2001:0:4136:e378:8000:63bf:3fff:fdd2"],
    "multicast": ["224.0.0.1", "239.255.255.250", "ff02::1", "ff05::2"],
    "reserved/broadcast": ["240.0.0.1", "255.255.255.255"],
    "documentation": ["192.0.2.1", "198.51.100.7", "203.0.113.9", "2001:db8::1", "3fff::1"],
    "benchmarking": ["198.18.0.1", "198.19.255.254"],
    "ietf protocol assignments": ["192.0.0.8", "192.0.0.192"],
    "6to4 relay anycast": ["192.88.99.1"],
    "discard-only": ["100::1"],
    "site-local": ["fec0::1"],
}
PRIVATE_CLASSES = {
    "loopback": ["127.0.0.1", "127.255.255.254", "::1"],
    "rfc1918": ["10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1"],
    "cgnat": ["100.64.0.1", "100.127.255.254"],
    "ipv6 unique-local": ["fc00::1", "fd12:3456:789a::1"],
    "nat64 of loopback": ["64:ff9b::7f00:1"],
}
PUBLIC = ["8.8.8.8", "1.1.1.1", PUBLIC_IP, "2606:4700:4700::1111", "64:ff9b::808:808"]


def _cases(classes: dict[str, list[str]]) -> list[object]:
    return [pytest.param(ip, id=f"{name}:{ip}") for name, ips in classes.items() for ip in ips]


@pytest.mark.parametrize("ip", _cases(BLOCKED_CLASSES))
def test_blocked_classes(ip: str) -> None:
    assert classify(ipaddress.ip_address(ip)) is AddressClass.BLOCKED


@pytest.mark.parametrize("ip", _cases(PRIVATE_CLASSES))
def test_private_classes(ip: str) -> None:
    assert classify(ipaddress.ip_address(ip)) is AddressClass.PRIVATE


@pytest.mark.parametrize("ip", PUBLIC)
def test_public_addresses(ip: str) -> None:
    assert classify(ipaddress.ip_address(ip)) is AddressClass.PUBLIC


# --- end to end through the adapter: blocked targets are never connected to ------------------


@pytest.mark.parametrize("ip", _cases({**BLOCKED_CLASSES, **PRIVATE_CLASSES}))
async def test_adapter_refuses_every_non_public_resolution(
    make_adapter: MakeAdapter, ip: str
) -> None:
    backend = FakeBackend(http_response())
    async with make_adapter(backend, resolver=static_resolver({HOST: [ip]})) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "never allowed" in response.error or "private address" in response.error
    assert ip not in response.error  # the user-facing error doesn't leak internal addresses
    assert backend.connects == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/chat",
        "http://[::1]/chat",
        "http://169.254.169.254/latest/meta-data/",
        "http://[fd00:ec2::254]/latest/meta-data/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0:8000/",
        "http://10.0.0.5/",
    ],
)
async def test_ip_literal_urls_are_checked_without_dns(make_adapter: MakeAdapter, url: str) -> None:
    lookups: list[str] = []
    backend = FakeBackend(http_response())
    async with make_adapter(backend, url=url, resolver=static_resolver({}, lookups)) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert backend.connects == []
    assert lookups == []


async def test_one_bad_address_blocks_the_whole_host(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response())
    resolver = static_resolver({HOST: [PUBLIC_IP, "10.0.0.7"]})
    async with make_adapter(backend, resolver=resolver) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert backend.connects == []


async def test_blocked_target_logs_the_address_server_side(
    make_adapter: MakeAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="agentprobe_core.adapters.ssrf")
    backend = FakeBackend()
    async with make_adapter(backend, resolver=static_resolver({HOST: ["169.254.169.254"]})) as a:
        await a.invoke("hi")
    assert "169.254.169.254" in caplog.text


async def test_blocked_is_not_retried(make_adapter: MakeAdapter) -> None:
    lookups: list[str] = []
    backend = FakeBackend()
    resolver = static_resolver({HOST: ["127.0.0.1"]}, lookups)
    async with make_adapter(backend, resolver=resolver, max_retries=3) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert lookups == [HOST]


@pytest.mark.parametrize("failure", [OSError("NXDOMAIN"), UnicodeError("label too long")])
async def test_unresolvable_host_is_an_error(make_adapter: MakeAdapter, failure: Exception) -> None:
    async def resolver(host: str, port: int) -> list[str]:
        raise failure

    backend = FakeBackend()
    async with make_adapter(backend, resolver=resolver, max_retries=0) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "could not resolve" in response.error


# --- pinning: connect to the validated address, verify TLS against the hostname -------------


async def test_connects_to_the_validated_address_with_hostname_for_tls(
    make_adapter: MakeAdapter,
) -> None:
    backend = FakeBackend(http_response())
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert backend.connects == [(PUBLIC_IP, 443)]
    [(server_hostname, ssl_context)] = backend.tls
    assert server_hostname == HOST  # SNI and certificate verification use the name
    assert ssl_context.check_hostname
    assert ssl_context.verify_mode.name == "CERT_REQUIRED"


async def test_dns_rebinding_cannot_swap_in_an_internal_address(
    make_adapter: MakeAdapter,
) -> None:
    """The attacker's DNS answers public first (to pass a check), then loopback. Each
    connection resolves exactly once and connects to what it validated."""
    answers = iter([[PUBLIC_IP], ["127.0.0.1"]])
    lookups = 0

    async def rebinding_resolver(host: str, port: int) -> list[str]:
        nonlocal lookups
        lookups += 1
        return next(answers)

    backend = FakeBackend(http_response(), http_response())
    async with make_adapter(backend, resolver=rebinding_resolver) as adapter:
        first = await adapter.invoke("hi")
        second = await adapter.invoke("hi")  # a new connection (the fake closes each one)
    assert first.error is None
    assert second.error is not None
    assert backend.connects == [(PUBLIC_IP, 443)]  # never 127.0.0.1
    assert lookups == 2  # one lookup per connection: nothing between check and connect


# --- the private-target opt-in needs both keys (and the allowlist, if set) --------------------


@pytest.mark.parametrize(
    ("agent_allows", "policy", "allowed"),
    [
        (False, TargetPolicy(), False),
        (True, TargetPolicy(), False),
        (False, TargetPolicy(allow_private=True), False),
        (True, TargetPolicy(allow_private=True), True),
        (True, TargetPolicy(allow_private=True, private_allowlist=frozenset({HOST})), True),
        (True, TargetPolicy(allow_private=True, private_allowlist=frozenset({"other"})), False),
        (False, TargetPolicy(allow_private=True, private_allowlist=frozenset({HOST})), False),
    ],
)
async def test_private_targets_need_agent_and_server_opt_in(
    make_adapter: MakeAdapter, agent_allows: bool, policy: TargetPolicy, allowed: bool
) -> None:
    backend = FakeBackend(http_response())
    resolver = static_resolver({HOST: ["10.1.2.3"]})
    async with make_adapter(
        backend, resolver=resolver, policy=policy, allow_private=agent_allows
    ) as adapter:
        response = await adapter.invoke("hi")
    assert (response.error is None) is allowed
    assert backend.connects == ([("10.1.2.3", 443)] if allowed else [])


@pytest.mark.parametrize("ip", ["169.254.169.254", "100.100.100.200", "fd00:ec2::254", "fe80::1"])
async def test_opt_in_never_opens_metadata_or_link_local(
    make_adapter: MakeAdapter, ip: str
) -> None:
    backend = FakeBackend(http_response())
    policy = TargetPolicy(allow_private=True)
    resolver = static_resolver({HOST: [ip]})
    async with make_adapter(
        backend, resolver=resolver, policy=policy, allow_private=True
    ) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert backend.connects == []


def test_policy_from_env() -> None:
    assert TargetPolicy.from_env({}) == TargetPolicy()
    assert not TargetPolicy.from_env({"ALLOW_PRIVATE_TARGETS": "true"}).allow_private
    policy = TargetPolicy.from_env(
        {"ALLOW_PRIVATE_TARGETS": "1", "PRIVATE_TARGET_ALLOWLIST": " Agent.Internal. , [::1],"}
    )
    assert policy.allow_private
    assert policy.private_allowlist == {"agent.internal", "::1"}
    assert policy.permits_private("AGENT.internal", agent_allows=True)


# --- redirects: off by default; when on, every hop is re-validated ----------------------------


async def test_redirects_are_off_by_default(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(302, headers=("Location: https://agent.example.com/x",)))
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "redirects are off" in response.error
    assert len(backend.connects) == 1


@pytest.mark.parametrize(
    "location",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:6379/",
        "http://[::1]/admin",
        "http://internal.corp/",  # a name that resolves to a private address
    ],
)
async def test_redirect_to_internal_is_blocked(make_adapter: MakeAdapter, location: str) -> None:
    backend = FakeBackend(http_response(302, headers=(f"Location: {location}",)), http_response())
    resolver = static_resolver({HOST: [PUBLIC_IP], "internal.corp": ["10.0.0.5"]})
    async with make_adapter(backend, resolver=resolver, follow_redirects=True) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert backend.connects == [(PUBLIC_IP, 443)]  # the internal hop never connected


@pytest.mark.parametrize("location", ["file:///etc/passwd", "gopher://agent.example.com/x"])
async def test_redirect_to_other_schemes_is_refused(
    make_adapter: MakeAdapter, location: str
) -> None:
    backend = FakeBackend(http_response(302, headers=(f"Location: {location}",)))
    async with make_adapter(backend, follow_redirects=True) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "not allowed" in response.error
    assert len(backend.connects) == 1


async def test_redirect_to_public_host_drops_secret_headers(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(
        http_response(307, headers=("Location: https://other.example.net/chat",)),
        http_response(body={"output": "moved"}),
    )
    resolver = static_resolver({HOST: [PUBLIC_IP], "other.example.net": [OTHER_PUBLIC_IP]})
    secret = {"X-Api-Key": SecretStr("sk-test-secret")}
    async with make_adapter(
        backend, resolver=resolver, follow_redirects=True, secret_headers=secret
    ) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert response.output == "moved"
    assert backend.connects == [(PUBLIC_IP, 443), (OTHER_PUBLIC_IP, 443)]
    first, second = backend.sent.split(b"POST /chat", 2)[1:]
    assert b"sk-test-secret" in first
    assert b"sk-test-secret" not in second


async def test_redirect_loop_stops(make_adapter: MakeAdapter) -> None:
    hop = http_response(302, headers=("Location: https://agent.example.com/chat",))
    backend = FakeBackend(*[hop] * 10)
    async with make_adapter(backend, follow_redirects=True) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "redirects" in response.error


# --- configuration-level checks --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://agent.example.com/",
        "file:///etc/passwd",
        "gopher://agent.example.com/",
        "https://user:pass@agent.example.com/",
        "not a url",
    ],
)
def test_config_rejects_bad_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        HttpAdapterConfig.model_validate({"url": url})


async def test_proxy_env_vars_cannot_bypass_the_guard(
    make_adapter: MakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://10.9.9.9:3128")
    backend = FakeBackend(http_response())
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert backend.connects == [(PUBLIC_IP, 443)]
