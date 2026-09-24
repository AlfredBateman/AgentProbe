import io
import json
import logging
from collections.abc import Iterator

import pytest

from agentprobe_api.logs import REDACTED, configure_logging, redact_query, request_id_var

API_KEY = "ap_" + "K" * 43  # fake credentials throughout
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLXZhbHVl"
PASSWORD = "hunter2-but-longer"
REFRESH = "r3fr3sh-" + "Q" * 30


@pytest.fixture
def output() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = configure_logging("DEBUG", stream)
    yield stream
    logging.getLogger().removeHandler(handler)


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def assert_clean(stream: io.StringIO) -> None:
    text = stream.getvalue()
    for secret in (API_KEY, JWT, PASSWORD, REFRESH):
        assert secret not in text, f"{secret[:8]}… leaked: {text}"


def test_output_is_one_json_object_per_record(output: io.StringIO) -> None:
    token = request_id_var.set("req-123")
    try:
        logging.getLogger("t").warning("hello %s", "world", extra={"status": 200})
    finally:
        request_id_var.reset(token)
    [entry] = lines(output)
    assert entry["msg"] == "hello world"
    assert entry["level"] == "WARNING"
    assert entry["request_id"] == "req-123"
    assert entry["status"] == 200


def test_sensitive_field_names_are_redacted(output: io.StringIO) -> None:
    logging.getLogger("t").info(
        "event",
        extra={
            "authorization": f"Bearer {API_KEY}",
            "cookie": f"access_token={JWT}; refresh_token={REFRESH}",
            "password": PASSWORD,
            "client_secret": "s",
            "refresh_token": REFRESH,
            "api_key": API_KEY,
            "headers": {"Authorization": f"Bearer {API_KEY}", "X-Trace": "ok"},
            "path": "/projects",
        },
    )
    [entry] = lines(output)
    for name in (
        "authorization",
        "cookie",
        "password",
        "client_secret",
        "refresh_token",
        "api_key",
    ):
        assert entry[name] == REDACTED
    assert entry["headers"] == {"Authorization": REDACTED, "X-Trace": "ok"}
    assert entry["path"] == "/projects"
    assert_clean(output)


def test_secret_values_in_free_text_are_scrubbed(output: io.StringIO) -> None:
    log = logging.getLogger("t")
    log.info("auth header was Bearer %s", API_KEY)
    log.info("got key %s and jwt %s", API_KEY, JWT)
    log.info("form: password=%s&email=a@example.com", PASSWORD)
    log.info("json: %s", json.dumps({"password": PASSWORD, "refresh_token": REFRESH}))
    log.info("cookie: access_token=%s; refresh_token=%s", JWT, REFRESH)
    assert_clean(output)
    assert "a@example.com" in output.getvalue()  # non-secret context survives


def test_tracebacks_are_scrubbed(output: io.StringIO) -> None:
    try:
        raise ValueError(f"bad credentials password={PASSWORD} key={API_KEY}")
    except ValueError:
        logging.getLogger("t").exception("failed")
    [entry] = lines(output)
    assert "ValueError" in str(entry["exc"])
    assert_clean(output)


def test_query_string_tokens_are_redacted() -> None:
    assert (
        redact_query(f"token={JWT}&page=2")
        == f"token={REDACTED.replace('[', '%5B').replace(']', '%5D')}&page=2"
    )
    assert JWT not in redact_query(f"a=1&stream_token={JWT}")
