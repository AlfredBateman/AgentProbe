"""SSRF guard for outbound requests to agents under test (SPEC.md §10, ADR 0012).

`GuardedBackend` sits under httpcore's connection pool, so it sees every new connection,
including each redirect hop and each retry. For every connection it resolves the host once,
validates every resolved address, and then connects to one of exactly those addresses. There
is no second lookup to race, so DNS rebinding can't swap an internal address in after the
check. TLS is unaffected: httpcore passes the URL's hostname to `start_tls` separately, so SNI
and certificate verification use the name, not the pinned address.

Address classes:
- public: allowed.
- private (loopback, RFC 1918, CGNAT, IPv6 unique-local): allowed only when the agent's config
  sets allow_private AND the server sets ALLOW_PRIVATE_TARGETS=1 AND, if
  PRIVATE_TARGET_ALLOWLIST is set, the host is on it.
- blocked (cloud metadata, link-local, unspecified, multicast, reserved and documentation
  ranges, IPv4-mapped/-compatible, 6to4 and Teredo): never allowed.
"""

import enum
import ipaddress
import logging
import os
import socket
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import anyio
import httpcore

log = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
# (host, port) -> resolved addresses. Injectable so tests can simulate DNS answers.
Resolver = Callable[[str, int], Awaitable[list[str]]]


def _nets(*cidrs: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(cidr) for cidr in cidrs)


# Cloud metadata and platform endpoints. Checked before _PRIVATE: some sit inside ranges that
# allow_private would otherwise open (Alibaba in CGNAT, AWS's IPv6 IMDS in unique-local).
_METADATA = _nets(
    "169.254.169.254/32",  # AWS, GCP, Azure, OCI, DigitalOcean, OpenStack
    "169.254.170.2/32",  # AWS ECS task metadata
    "169.254.170.23/32",  # AWS EKS pod identity
    "100.100.100.200/32",  # Alibaba Cloud
    "168.63.129.16/32",  # Azure WireServer (a public address)
    "fd00:ec2::/32",  # AWS IPv6 IMDS (fd00:ec2::254) and EKS pod identity (fd00:ec2::23)
)
_PRIVATE = _nets(
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",  # CGNAT
    "::1/128",
    "fc00::/7",  # unique-local
)
# Explicit because `is_global` alone lets some of these through (multicast, site-local,
# IPv4-compatible); `is_global` still runs afterwards for anything not listed.
_BLOCKED = _nets(
    "0.0.0.0/8",  # "this network"; 0.0.0.0 reaches localhost on Linux
    "169.254.0.0/16",  # link-local
    "192.0.0.0/24",  # IETF protocol assignments
    "192.0.2.0/24",  # TEST-NET-1
    "192.88.99.0/24",  # 6to4 relay anycast
    "198.18.0.0/15",  # benchmarking
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",  # TEST-NET-3
    "224.0.0.0/4",  # multicast
    "240.0.0.0/4",  # reserved, including broadcast
    "::/96",  # unspecified and IPv4-compatible (deprecated)
    "64:ff9b:1::/48",  # local-use NAT64
    "100::/64",  # discard-only
    "2001::/23",  # IETF protocol assignments, including Teredo (2001::/32)
    "2001:db8::/32",  # documentation
    "2002::/16",  # 6to4
    "3fff::/20",  # documentation
    "fe80::/10",  # link-local
    "fec0::/10",  # site-local (deprecated)
    "ff00::/8",  # multicast
)
# Well-known NAT64 prefix: the low 32 bits are an IPv4 address that the gateway reaches.
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")


class AddressClass(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    BLOCKED = "blocked"


def classify(ip: IPAddress) -> AddressClass:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return AddressClass.BLOCKED  # ::ffff:a.b.c.d: OS-dependent routing, no use here
        if ip in _NAT64:
            return classify(ipaddress.IPv4Address(int(ip) & 0xFFFF_FFFF))
    if any(ip in net for net in _METADATA):
        return AddressClass.BLOCKED
    if any(ip in net for net in _PRIVATE):
        return AddressClass.PRIVATE
    if any(ip in net for net in _BLOCKED) or not ip.is_global:
        return AddressClass.BLOCKED
    return AddressClass.PUBLIC


def _normalize_host(host: str) -> str:
    return host.strip().strip("[]").rstrip(".").lower()


@dataclass(frozen=True)
class TargetPolicy:
    """The server's half of the private-target opt-in; the agent's config holds the other."""

    allow_private: bool = False
    private_allowlist: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TargetPolicy":
        env = os.environ if env is None else env
        hosts = env.get("PRIVATE_TARGET_ALLOWLIST", "").split(",")
        return cls(
            allow_private=env.get("ALLOW_PRIVATE_TARGETS") == "1",
            private_allowlist=frozenset(_normalize_host(h) for h in hosts if h.strip()),
        )

    def permits_private(self, host: str, *, agent_allows: bool) -> bool:
        return (
            agent_allows
            and self.allow_private
            and (not self.private_allowlist or _normalize_host(host) in self.private_allowlist)
        )


class TargetBlocked(Exception):
    """The target is not allowed by the SSRF policy. Deterministic, so never retried."""


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def resolve_target(
    host: str, port: int, *, policy: TargetPolicy, agent_allows_private: bool, resolver: Resolver
) -> list[str]:
    """Resolves `host` and returns its addresses if every one of them is allowed."""
    try:
        addresses: list[IPAddress] = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            answers = await resolver(host, port)
        except (OSError, UnicodeError) as exc:  # UnicodeError: a name IDNA can't encode
            raise httpcore.ConnectError(f"could not resolve {host}") from exc
        addresses = [ipaddress.ip_address(a) for a in dict.fromkeys(answers)]
    if not addresses:
        raise httpcore.ConnectError(f"could not resolve {host}")
    for ip in addresses:
        verdict = classify(ip)
        if verdict is AddressClass.PUBLIC or (
            verdict is AddressClass.PRIVATE
            and policy.permits_private(host, agent_allows=agent_allows_private)
        ):
            continue
        # The address goes to the server log only; the error the user sees omits it.
        log.warning("ssrf guard blocked %s: %s address %s", host, verdict.value, ip)
        if verdict is AddressClass.PRIVATE:
            raise TargetBlocked(
                f"{host} resolves to a private address. Private targets need allow_private "
                "on the agent, ALLOW_PRIVATE_TARGETS=1 on the server and, if "
                "PRIVATE_TARGET_ALLOWLIST is set, the host on that list"
            )
        raise TargetBlocked(f"{host} resolves to a reserved or internal address (never allowed)")
    return [str(ip) for ip in addresses]


class GuardedBackend(httpcore.AsyncNetworkBackend):
    """Validates every connection's target, then connects to the validated address."""

    def __init__(
        self,
        *,
        policy: TargetPolicy,
        agent_allows_private: bool,
        resolver: Resolver = system_resolver,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._agent_allows_private = agent_allows_private
        self._resolver = resolver
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore's backend interface)
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                addresses = await resolve_target(
                    host,
                    port,
                    policy=self._policy,
                    agent_allows_private=self._agent_allows_private,
                    resolver=self._resolver,
                )
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout(f"resolving {host} timed out") from exc
        # ponytail: addresses are tried in order, not raced (Happy Eyeballs), so a black-holed
        # IPv6 address can use up the connect timeout; race them if dual-stack targets need it.
        error: Exception = httpcore.ConnectError(f"could not connect to {host}")
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address, port, timeout, local_address, socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                error = exc
        raise error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore's backend interface)
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise TargetBlocked("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)
