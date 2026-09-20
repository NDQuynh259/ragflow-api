"""Core security principal and execution context abstractions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import ForbiddenException


@dataclass(frozen=True)
class CurrentPrincipal:
    """Security principal representing the authenticated caller and their granted capabilities."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    active_workspace_id: uuid.UUID | None = None
    token: str = ""
    role: str | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_owner(self) -> bool:
        """Check if principal is the workspace owner."""
        return self.role == "owner"

    def has_permission(self, permission: str | Any) -> bool:
        """Check if principal possesses a specific permission or wildcard access."""
        if self.is_owner:
            return True
        perm_key = str(getattr(permission, "value", permission))
        return "*" in self.permissions or perm_key in self.permissions

    def has_any_permission(self, *permissions: str | Any) -> bool:
        """Check if principal possesses at least one of the specified permissions (OR check)."""
        if self.is_owner:
            return True
        return any(self.has_permission(p) for p in permissions)

    def has_all_permissions(self, *permissions: str | Any) -> bool:
        """Check if principal possesses all of the specified permissions (AND check)."""
        if self.is_owner:
            return True
        return all(self.has_permission(p) for p in permissions)

    def has_role(self, *roles: str) -> bool:
        """Check if principal matches any of the specified roles."""
        return self.role in roles

    def require_permission(self, *permissions: str | Any) -> None:
        """Assert that caller possesses ALL listed permissions (AND check).

        Raises ForbiddenException (403) if any permission is missing.
        """
        if self.is_owner:
            return
        for perm in permissions:
            if not self.has_permission(perm):
                perm_key = str(getattr(perm, "value", perm))
                raise ForbiddenException(f"Missing required permission: '{perm_key}'")

    def require_any_permission(self, *permissions: str | Any) -> None:
        """Assert that caller possesses AT LEAST ONE of the listed permissions (OR check).

        Raises ForbiddenException (403) if none of the permissions are granted.
        """
        if self.is_owner:
            return
        if not self.has_any_permission(*permissions):
            keys = ", ".join(str(getattr(p, "value", p)) for p in permissions)
            raise ForbiddenException(
                f"Missing required permission. Requires at least one of: [{keys}]"
            )

    def require_role(self, *roles: str) -> None:
        """Assert that caller has one of the specified roles.

        Raises ForbiddenException (403) if role does not match.
        """
        if not self.has_role(*roles):
            raise ForbiddenException(f"User requires one of roles: {roles}, but has '{self.role}'")


@dataclass(frozen=True)
class ExecutionContext:
    """Context holding ambient request information and the current security principal."""

    principal: CurrentPrincipal | None = None
    request_id: str | None = None
