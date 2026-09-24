"""Password hashing, JWTs, API keys and refresh tokens (ADR 0009)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import SecretStr

API_KEY_PREFIX = "ap_"
TokenType = Literal["access", "stream"]
_ALGORITHM = "HS256"
_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters
# Verified against when the email is unknown, so login timing doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class InvalidToken(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """password_hash=None (unknown user) still costs one full verify."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def encode_token(
    secret: SecretStr, typ: TokenType, subject: uuid.UUID, ttl: timedelta, **claims: Any
) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(subject), "typ": typ, "iat": now, "exp": now + ttl, **claims}
    return jwt.encode(payload, secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_token(secret: SecretStr, typ: TokenType, token: str) -> dict[str, Any]:
    """Raises InvalidToken on a bad signature, expiry, missing claim or the wrong type.

    The type check is what stops a stream token being used as an access token (and back).
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            secret.get_secret_value(),
            algorithms=[_ALGORITHM],  # fixed list: no alg=none or algorithm confusion
            options={"require": ["sub", "typ", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if claims["typ"] != typ:
        raise InvalidToken("wrong token type")
    return claims
