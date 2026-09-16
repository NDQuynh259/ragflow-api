"""Password hashing and cryptographic session token generation."""

from __future__ import annotations

import hashlib
import secrets
import bcrypt


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def generate_session_token() -> str:
    """Generate a cryptographically secure URL-safe session token (32 bytes entropy)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Return the stable digest stored for an opaque session credential."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
