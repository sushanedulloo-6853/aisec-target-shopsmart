from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from shopsmart.config import get_settings
from shopsmart.db import get_db
from shopsmart.models import User

_PBKDF2_ROUNDS = 240_000
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, expected = stored.split("$", 3)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
    return hmac.compare_digest(digest.hex(), expected)


@dataclass(frozen=True)
class Principal:
    user_id: int
    role: str
    merchant_id: int | None
    email: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "merchant_id": user.merchant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None
    user = db.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return Principal(user_id=user.id, role=user.role, merchant_id=user.merchant_id, email=user.email)


def require_role(*roles: str):
    def checker(principal: Principal = Depends(get_current_user)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    return checker


class SlidingWindowLimiter:
    """Small in-process limiter. Good enough for a single container."""

    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > self.per_seconds:
            window.popleft()
        if len(window) >= self.max_calls:
            return False
        window.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


login_limiter = SlidingWindowLimiter(max_calls=10, per_seconds=60)


def enforce_login_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not login_limiter.hit(client):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts, slow down")
