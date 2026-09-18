"""Password hashing and bearer-token auth. Stdlib only — no extra crypto
dependency needed for a mock store that will be replaced later."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db.models import TokenModel, UserModel
from .db.session import get_db
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


async def get_current_user(db: Session = Depends(get_db), token: str = Depends(get_bearer_token)) -> User:
    # Queries the DB directly (not via Store) to avoid a security<->store
    # import cycle — Store already depends on hash_password/verify_password.
    token_row = db.get(TokenModel, token)
    user_row = db.get(UserModel, token_row.user_id) if token_row else None
    if user_row is None:
        raise UnauthorizedError("Invalid or expired token.")
    return User(id=user_row.id, name=user_row.name, email=user_row.email, avatar_initials=user_row.avatar_initials)
