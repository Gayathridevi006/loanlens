from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.types import Text, TypeDecorator

from .database import get_db


_bearer = HTTPBearer(auto_error=False)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(password.encode())
    return f"scrypt$16384$8$1${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = Scrypt(salt=_unb64(salt), length=32, n=int(n), r=int(r), p=int(p)).derive(password.encode())
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> bytes:
    return os.getenv("JWT_SECRET", "loanlens-development-secret-change-in-production").encode()


def create_access_token(subject: str, role: str, expires_minutes: int = 30) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": subject, "role": role, "iat": now, "exp": now + expires_minutes * 60}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_jwt_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(_jwt_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            raise ValueError("invalid signature")
        claims = json.loads(_unb64(payload))
        if int(claims["exp"]) < int(time.time()):
            raise ValueError("expired")
        return claims
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Invalid or expired access token") from exc


@dataclass(frozen=True)
class AuthContext:
    username: str
    role: str


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if credentials is None:
        if os.getenv("AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}:
            raise HTTPException(401, "Authentication required")
        return AuthContext("local-admin", "admin")
    claims = decode_access_token(credentials.credentials)
    from .models import User
    user = db.query(User).filter(User.username == claims.get("sub")).first()
    if not user or user.role != claims.get("role"):
        raise HTTPException(401, "User is no longer authorized")
    return AuthContext(user.username, user.role)


def require_roles(*roles: str) -> Callable:
    def dependency(user: AuthContext = Depends(current_user)) -> AuthContext:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return dependency


def _fernet() -> Fernet:
    configured = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    if configured:
        return Fernet(configured.encode())
    # Local-development compatibility. Production must provide a secret key.
    digest = hashlib.sha256(b"loanlens-local-development-only").digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedJSON(TypeDecorator):
    """Encrypt JSON at rest while exposing ordinary Python structures."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str:
        payload = json.dumps(value if value is not None else {}, default=str, separators=(",", ":"))
        return _fernet().encrypt(payload.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> Any:
        if not value:
            return {}
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(_fernet().decrypt(value.encode()).decode())
        except (InvalidToken, ValueError, json.JSONDecodeError):
            # Supports migration from the prototype's plaintext JSON rows.
            try:
                return json.loads(value) if isinstance(value, str) else value
            except (TypeError, json.JSONDecodeError):
                return {}


class EncryptedText(TypeDecorator):
    """Encrypt potentially sensitive extracted document text at rest."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str:
        return _fernet().encrypt(str(value or "").encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str:
        if not value:
            return ""
        try:
            return _fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            return value
