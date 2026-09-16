"""Unit tests for core.auth (password, tokens, CurrentPrincipal)."""

from __future__ import annotations

import uuid
import pytest

from core.auth import (
    CurrentPrincipal,
    ExecutionContext,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from core.exceptions import ForbiddenException


def test_password_hashing_and_verification():
    raw = "SuperSecretPassword123!"
    hashed = hash_password(raw)

    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_token_generation_and_hashing():
    token1 = generate_session_token()
    token2 = generate_session_token()

    assert token1 != token2
    assert len(token1) > 20

    hash1 = hash_session_token(token1)
    hash2 = hash_session_token(token1)
    assert hash1 == hash2
    assert hash_session_token(token2) != hash1


def test_current_principal_permissions():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    # Member principal
    member = CurrentPrincipal(
        user_id=user_id,
        session_id=session_id,
        role="member",
        permissions=frozenset({"documents:read", "messages:send"}),
    )

    assert member.is_owner is False
    assert member.has_permission("documents:read") is True
    assert member.has_permission("documents:delete") is False
    assert member.has_any_permission("documents:delete", "messages:send") is True
    assert member.has_all_permissions("documents:read", "messages:send") is True
    assert member.has_all_permissions("documents:read", "documents:delete") is False

    # Successful assertion
    member.require_permission("documents:read")

    # Missing permission raises ForbiddenException
    with pytest.raises(ForbiddenException):
        member.require_permission("documents:delete")

    with pytest.raises(ForbiddenException):
        member.require_any_permission("documents:delete", "workspace:manage_members")


def test_current_principal_owner_bypass():
    owner = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="owner",
        permissions=frozenset(),
    )

    assert owner.is_owner is True
    # Owner automatically bypasses all permission checks
    assert owner.has_permission("any:arbitrary:permission") is True
    assert owner.has_all_permissions("perm1", "perm2") is True
    assert owner.has_any_permission("perm3") is True

    # None of these should raise
    owner.require_permission("perm1")
    owner.require_any_permission("perm2")


def test_execution_context():
    principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    ctx = ExecutionContext(principal=principal, request_id="req-12345")
    assert ctx.principal == principal
    assert ctx.request_id == "req-12345"
