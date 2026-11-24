"""Password hashing (stdlib scrypt) and session tokens. No third-party crypto needed.

Hash format: scrypt$<n>$<r>$<p>$<salt b64>$<key b64>
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
from functools import cache

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16


class MalformedPasswordHashError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=64 * 1024 * 1024
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            raise ValueError(f"unknown scheme {scheme!r}")
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(key_b64, validate=True)
        actual = _scrypt(password, salt, int(n), int(r), int(p), len(expected))
    except ValueError as exc:
        raise MalformedPasswordHashError("stored password hash is malformed") from exc
    return hmac.compare_digest(actual, expected)


@cache
def dummy_hash() -> str:
    """Verified against when the user doesn't exist, so login timing doesn't reveal emails."""
    return hash_password(secrets.token_urlsafe(16))


# scrypt is CPU-bound (~50 ms): keep it off the event loop.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, stored: str) -> bool:
    return await asyncio.to_thread(verify_password, password, stored)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """What we store in the DB: a stolen DB dump can't be replayed as cookies."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()
