"""
security.py — Password hashing (argon2) and JWT creation / verification.
No secrets or tokens are ever logged (see RULES.md).
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import settings

logger = logging.getLogger(__name__)

# argon2-cffi hasher with library defaults (good for 2024+).
_ph = PasswordHasher()


# ── Password helpers ───────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return an argon2 hash of *plain*. Never log the input."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if *plain* matches *hashed*, False otherwise.
    Absorbs all argon2 exceptions so callers always get a bool.
    """
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ── JWT helpers ────────────────────────────────────────────────────────

_ALGORITHM = "HS256"
_TOKEN_TYPE = "access"


def create_access_token(user_id: str) -> str:
    """
    Create a signed JWT containing the user's UUID as 'sub'.
    Expiry is controlled by JWT_EXPIRE_MINUTES in settings.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT. Raises jwt.PyJWTError on any failure
    (expired, tampered, wrong algorithm, etc.).
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])
