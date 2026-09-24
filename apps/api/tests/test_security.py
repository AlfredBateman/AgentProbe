import uuid
from datetime import timedelta

import jwt
import pytest
from pydantic import SecretStr

from agentprobe_api.security import (
    InvalidToken,
    decode_token,
    encode_token,
    hash_password,
    new_api_key,
    sha256,
    verify_password,
)

SECRET = SecretStr("unit-test-secret-" + "y" * 32)
USER = uuid.uuid4()
PASSWORD = "correct horse battery staple"  # fake credential


def test_password_round_trip() -> None:
    stored = hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert verify_password(stored, PASSWORD)
    assert not verify_password(stored, PASSWORD + "!")


def test_unknown_user_never_verifies() -> None:
    assert not verify_password(None, PASSWORD)
    assert not verify_password("not-a-hash", PASSWORD)


def test_token_round_trip() -> None:
    token = encode_token(SECRET, "access", USER, timedelta(minutes=5))
    assert decode_token(SECRET, "access", token)["sub"] == str(USER)


def test_stream_token_carries_scope_claims() -> None:
    run_id = str(uuid.uuid4())
    token = encode_token(SECRET, "stream", USER, timedelta(seconds=60), run_id=run_id)
    assert decode_token(SECRET, "stream", token)["run_id"] == run_id


@pytest.mark.parametrize(("minted", "expected"), [("access", "stream"), ("stream", "access")])
def test_token_types_are_not_interchangeable(minted: str, expected: str) -> None:
    token = encode_token(SECRET, minted, USER, timedelta(minutes=5))  # type: ignore[arg-type]
    with pytest.raises(InvalidToken, match="wrong token type"):
        decode_token(SECRET, expected, token)  # type: ignore[arg-type]


def test_expired_token_rejected() -> None:
    token = encode_token(SECRET, "access", USER, timedelta(seconds=-1))
    with pytest.raises(InvalidToken):
        decode_token(SECRET, "access", token)


def test_wrong_secret_rejected() -> None:
    token = encode_token(
        SecretStr("another-secret-" + "z" * 32), "access", USER, timedelta(minutes=5)
    )
    with pytest.raises(InvalidToken):
        decode_token(SECRET, "access", token)


def test_alg_none_rejected() -> None:
    token = jwt.encode(
        {"sub": str(USER), "typ": "access", "iat": 0, "exp": 2**40}, None, algorithm="none"
    )
    with pytest.raises(InvalidToken):
        decode_token(SECRET, "access", token)


def test_missing_type_claim_rejected() -> None:
    token = jwt.encode(
        {"sub": str(USER), "iat": 0, "exp": 2**40}, SECRET.get_secret_value(), algorithm="HS256"
    )
    with pytest.raises(InvalidToken):
        decode_token(SECRET, "access", token)


def test_api_key_shape() -> None:
    key = new_api_key()
    assert key.startswith("ap_")
    assert len(key) >= 40
    assert key != new_api_key()
    assert len(sha256(key)) == 64
