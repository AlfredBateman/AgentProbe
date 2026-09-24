"""Fernet encryption for the `secrets` table (ADR 0003). Never logs anything."""

from cryptography.fernet import Fernet
from pydantic import SecretStr


class SecretBox:
    def __init__(self, key: str | SecretStr) -> None:
        raw = key.get_secret_value() if isinstance(key, SecretStr) else key
        self._fernet = Fernet(raw)  # ValueError on a malformed key

    def __repr__(self) -> str:
        return "SecretBox(key=<redacted>)"

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> SecretStr:
        """Raises cryptography.fernet.InvalidToken on a wrong key or tampered data.

        Returns a SecretStr so the value is masked in repr/str/logs; call
        .get_secret_value() only where the outgoing request is built.
        """
        return SecretStr(self._fernet.decrypt(ciphertext).decode())
