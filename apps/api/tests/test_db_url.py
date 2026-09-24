import pytest

from agentprobe_api.db import normalize_url

NEON = "postgresql://u:p@ep-x-123.eu-central-1.aws.neon.tech/app?sslmode=require&channel_binding=require"


def test_neon_string_pasted_as_is() -> None:
    assert normalize_url(NEON) == NEON.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_scheme_rewritten_to_psycopg(scheme: str) -> None:
    url = normalize_url(f"{scheme}://u:p@db.example.com/app?sslmode=verify-full")
    assert url == "postgresql+psycopg://u:p@db.example.com/app?sslmode=verify-full"


def test_remote_host_defaults_to_tls() -> None:
    assert normalize_url("postgresql://u:p@db.example.com/app").endswith("?sslmode=require")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_local_host_left_without_tls(host: str) -> None:
    assert normalize_url(f"postgresql://u:p@{host}:5432/app") == (
        f"postgresql+psycopg://u:p@{host}:5432/app"
    )


def test_other_schemes_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        normalize_url("mysql://u:p@db.example.com/app")
