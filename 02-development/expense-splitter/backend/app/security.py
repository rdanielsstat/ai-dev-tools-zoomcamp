"""Password hashing and bearer-token auth. Stdlib only — no extra crypto
dependency needed for a mock store that will be replaced later."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import UnauthorizedError
from .schemas import User

_PBKDF2_ITERATIONS = 200_000

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt_hex, digest_hex = stored_hash.split(":")
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    return credentials.credentials


async def get_current_user(request: Request, token: str = Depends(get_bearer_token)) -> User:
    store = request.app.state.store
    user = store.user_for_token(token)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    return user
