"""Cryptographic token generation and stable hashing utilities."""

from __future__ import annotations

import hashlib
import secrets


def generate_session_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure URL-safe token (default 32 bytes entropy)."""
    return secrets.token_urlsafe(nbytes)


def hash_session_token(token: str) -> str:
    """Return the SHA-256 stable digest stored for an opaque session credential."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
