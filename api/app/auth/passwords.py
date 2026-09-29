"""argon2id with the spec parameters: time 3, memory 64 MiB, parallelism 2 (section 15)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


def hash_secret(secret: str) -> str:
    return _hasher.hash(secret)


def verify_secret(hashed: str, secret: str) -> bool:
    try:
        return _hasher.verify(hashed, secret)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
