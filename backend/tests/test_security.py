from __future__ import annotations

import pytest

from app.security import (
    MalformedPasswordHashError,
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)


def test_hash_roundtrip() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("correct horse batterY", stored)


def test_hashes_are_salted() -> None:
    assert hash_password("same password!") != hash_password("same password!")


def test_unicode_password() -> None:
    stored = hash_password("รหัสผ่านภาษาไทย123")
    assert verify_password("รหัสผ่านภาษาไทย123", stored)


@pytest.mark.parametrize(
    "stored",
    ["", "plain", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$16384$8$1$!!$AAAA"],
)
def test_malformed_hash_raises(stored: str) -> None:
    with pytest.raises(MalformedPasswordHashError):
        verify_password("whatever", stored)


def test_session_tokens_are_random_and_digest_is_stable() -> None:
    a, b = new_session_token(), new_session_token()
    assert a != b
    assert len(a) >= 40
    assert token_digest(a) == token_digest(a)
    assert len(token_digest(a)) == 64
