"""Pinning the validated address must not weaken TLS: a real handshake against a local server
(connected to by IP) still sends the hostname as SNI and verifies the certificate against it.
Offline: loopback only, with a throwaway CA.
"""

import asyncio
import datetime as dt
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from adapterfakes import static_resolver
from agentprobe_core.adapters import HttpAdapter, HttpAdapterConfig, TargetPolicy

HOST = "agent.test"


def _cert(
    subject: str,
    key: ec.EllipticCurvePrivateKey,
    issuer: x509.Certificate | None,
    ca_key: ec.EllipticCurvePrivateKey,
) -> x509.Certificate:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
    now = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer.subject if issuer else name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
    )
    if issuer is None:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
    else:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(subject)]), False)
    return builder.sign(ca_key, hashes.SHA256())


def _pem(path: Path, *items: x509.Certificate | ec.EllipticCurvePrivateKey) -> Path:
    chunks = [
        item.public_bytes(serialization.Encoding.PEM)
        if isinstance(item, x509.Certificate)
        else item.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        for item in items
    ]
    path.write_bytes(b"".join(chunks))
    return path


# Starts a TLS server whose certificate names the given host: (port, SNI names it saw).
Start = Callable[[str], Awaitable[tuple[int, list[str | None]]]]


@pytest.fixture
async def tls_server(tmp_path: Path) -> AsyncIterator[tuple[ssl.SSLContext, Start]]:
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = _cert("AgentProbe Test CA", ca_key, None, ca_key)
    client_ctx = ssl.create_default_context(cafile=str(_pem(tmp_path / "ca.pem", ca)))
    servers: list[asyncio.Server] = []

    async def start(cert_name: str) -> tuple[int, list[str | None]]:
        key = ec.generate_private_key(ec.SECP256R1())
        leaf = _cert(cert_name, key, ca, ca_key)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(_pem(tmp_path / f"{cert_name}.pem", leaf, key))
        seen_sni: list[str | None] = []
        server_ctx.sni_callback = lambda _sock, name, _ctx: seen_sni.append(name)

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                head = await reader.readuntil(b"\r\n\r\n")
                length = int(
                    next(
                        line.split(b":", 1)[1]
                        for line in head.split(b"\r\n")
                        if line.lower().startswith(b"content-length:")
                    )
                )
                await reader.readexactly(length)
                body = b'{"output": "hello over tls"}'
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
            except (ssl.SSLError, ConnectionError, asyncio.IncompleteReadError):
                pass  # the client rejected our certificate
            finally:
                writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_ctx)
        servers.append(server)
        return server.sockets[0].getsockname()[1], seen_sni

    yield client_ctx, start
    for server in servers:
        server.close()
        await server.wait_closed()


async def _call(client_ctx: ssl.SSLContext, port: int) -> str | None:
    config = HttpAdapterConfig(
        url=f"https://{HOST}:{port}/chat", allow_private=True, max_retries=0, timeout_ms=5_000
    )
    async with HttpAdapter(
        config,
        policy=TargetPolicy(allow_private=True),
        ssl_context=client_ctx,
        resolver=static_resolver({HOST: ["127.0.0.1"]}),
    ) as adapter:
        response = await adapter.invoke("hi")
    return response.error if response.error else response.output


async def test_tls_uses_the_hostname_while_connecting_to_the_pinned_ip(
    tls_server: tuple[ssl.SSLContext, Start],
) -> None:
    client_ctx, start = tls_server
    port, seen_sni = await start(HOST)
    assert await _call(client_ctx, port) == "hello over tls"
    assert seen_sni == [HOST]


async def test_certificate_for_another_name_is_rejected(
    tls_server: tuple[ssl.SSLContext, Start],
) -> None:
    client_ctx, start = tls_server
    port, _ = await start("other.test")
    result = await _call(client_ctx, port)
    assert result is not None
    assert result.startswith("TLS failed")  # classified as permanent, not retried
    assert "CERTIFICATE_VERIFY_FAILED" in result
    assert "Hostname mismatch" in result
