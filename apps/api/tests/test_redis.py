import os
import socket
from urllib.parse import urlsplit

import pytest


@pytest.mark.redis
def test_redis_answers_ping() -> None:
    # ponytail: raw RESP PING, no client dependency; switch to arq's client at B2.3.
    url = urlsplit(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    with socket.create_connection((url.hostname or "localhost", url.port or 6379), timeout=5) as s:
        s.sendall(b"PING\r\n")
        assert s.recv(16) == b"+PONG\r\n"
