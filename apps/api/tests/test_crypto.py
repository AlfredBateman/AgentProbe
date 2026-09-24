import logging

import pytest
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from agentprobe_api.crypto import SecretBox

PLAINTEXT = "Bearer fake-token-123"  # fake data only


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip(key: str) -> None:
    box = SecretBox(key)
    assert box.decrypt(box.encrypt(PLAINTEXT)).get_secret_value() == PLAINTEXT


def test_accepts_secretstr_key(key: str) -> None:
    box = SecretBox(SecretStr(key))
    assert box.decrypt(box.encrypt(PLAINTEXT)).get_secret_value() == PLAINTEXT


def test_ciphertext_is_randomized_and_opaque(key: str) -> None:
    box = SecretBox(key)
    a, b = box.encrypt(PLAINTEXT), box.encrypt(PLAINTEXT)
    assert a != b
    assert PLAINTEXT.encode() not in a


def test_wrong_key_fails(key: str) -> None:
    token = SecretBox(key).encrypt(PLAINTEXT)
    with pytest.raises(InvalidToken):
        SecretBox(Fernet.generate_key().decode()).decrypt(token)


def test_tampered_ciphertext_fails(key: str) -> None:
    box = SecretBox(key)
    token = bytearray(box.encrypt(PLAINTEXT))
    token[-5] ^= 0x01
    with pytest.raises(InvalidToken):
        box.decrypt(bytes(token))


def test_malformed_key_rejected() -> None:
    with pytest.raises(ValueError):
        SecretBox("not-a-fernet-key")


def test_nothing_sensitive_in_repr_or_logs(key: str, caplog: pytest.LogCaptureFixture) -> None:
    box = SecretBox(key)
    value = box.decrypt(box.encrypt(PLAINTEXT))
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("test").info("box=%r value=%s value=%r", box, value, value)
    rendered = [repr(box), str(box), repr(value), str(value), f"{value}", caplog.text]
    for text in rendered:
        assert PLAINTEXT not in text
        assert key not in text
