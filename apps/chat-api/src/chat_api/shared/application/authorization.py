"""Authorization primitives and permission catalog (inspired by ViShop architecture)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid

from chat_api.shared.domain.uow import UnitOfWork
from core.exceptions import ForbiddenException


class Permission(str, Enum):
    """Fine-grained permission keys across application domains."""

    # Workspaces
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_UPDATE = "workspace:update"
    WORKSPACE_DELETE = "workspace:delete"
    WORKSPACE_MANAGE_MEMBERS = "workspace:manage_members"

    # Documents
    DOCUMENT_READ = "documents:read"
    DOCUMENT_CREATE = "documents:create"
    DOCUMENT_DELETE = "documents:delete"

    # Sessions & Messages
    SESSION_READ = "sessions:read"
    SESSION_CREATE = "sessions:create"
    SESSION_UPDATE = "sessions:update"
    SESSION_DELETE = "sessions:delete"
    MESSAGE_SEND = "messages:send"


@dataclass(frozen=True)
class PermissionItem:
    """Metadata item describing a permission in the catalog."""

    code: str
    name: str
    description: str
    module: str


# Single source of truth for all system permissions
PERMISSION_CATALOG: tuple[PermissionItem, ...] = (
    PermissionItem(
        code=Permission.WORKSPACE_READ.value,
        name="Xem không gian làm việc",
        description="Xem thông tin chi tiết và danh sách thành viên không gian làm việc",
        module="workspace",
    ),
    PermissionItem(
        code=Permission.WORKSPACE_UPDATE.value,
        name="Cập nhật không gian làm việc",
        description="Chỉnh sửa thông tin và cấu hình của không gian làm việc",
        module="workspace",
    ),
    PermissionItem(
        code=Permission.WORKSPACE_DELETE.value,
        name="Xóa không gian làm việc",
        description="Xóa vĩnh viễn không gian làm việc (Chỉ dành cho Owner)",
        module="workspace",
    ),
    PermissionItem(
        code=Permission.WORKSPACE_MANAGE_MEMBERS.value,
        name="Quản lý thành viên",
        description="Mời, gán vai trò hoặc xóa thành viên khỏi không gian làm việc",
        module="workspace",
    ),
    PermissionItem(
        code=Permission.DOCUMENT_READ.value,
        name="Xem tài liệu",
        description="Xem danh sách và nội dung tài liệu trong kho lưu trữ",
        module="documents",
    ),
    PermissionItem(
        code=Permission.DOCUMENT_CREATE.value,
        name="Tải lên tài liệu",
        description="Tải lên và xử lý tài liệu mới vào hệ thống RAG",
        module="documents",
    ),
    PermissionItem(
        code=Permission.DOCUMENT_DELETE.value,
        name="Xóa tài liệu",
        description="Xóa tài liệu và các vector embeddings liên quan",
        module="documents",
    ),
    PermissionItem(
        code=Permission.SESSION_READ.value,
        name="Xem phiên hội thoại",
        description="Xem lịch sử các phiên chat và tài liệu đính kèm",
        module="sessions",
    ),
    PermissionItem(
        code=Permission.SESSION_CREATE.value,
        name="Tạo phiên hội thoại",
        description="Tạo phiên chat mới và cấu hình RAG cho phiên",
        module="sessions",
    ),
    PermissionItem(
        code=Permission.SESSION_UPDATE.value,
        name="Cập nhật phiên hội thoại",
        description="Đổi tên hoặc cập nhật cấu hình RAG của phiên chat",
        module="sessions",
    ),
    PermissionItem(
        code=Permission.SESSION_DELETE.value,
        name="Xóa phiên hội thoại",
        description="Xóa phiên chat và toàn bộ tin nhắn liên quan",
        module="sessions",
    ),
    PermissionItem(
        code=Permission.MESSAGE_SEND.value,
        name="Gửi tin nhắn chat",
        description="Đặt câu hỏi và nhận câu trả lời RAG từ AI",
        module="messages",
    ),
)

ALL_PERMISSION_CODES: frozenset[str] = frozenset(item.code for item in PERMISSION_CATALOG)

BUILTIN_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": ALL_PERMISSION_CODES,  # Full system & workspace access
    "admin": frozenset(
        {
            Permission.WORKSPACE_READ.value,
            Permission.WORKSPACE_UPDATE.value,
            Permission.WORKSPACE_MANAGE_MEMBERS.value,
            Permission.DOCUMENT_READ.value,
            Permission.DOCUMENT_CREATE.value,
            Permission.DOCUMENT_DELETE.value,
            Permission.SESSION_READ.value,
            Permission.SESSION_CREATE.value,
            Permission.SESSION_UPDATE.value,
            Permission.SESSION_DELETE.value,
            Permission.MESSAGE_SEND.value,
        }
    ),
    "member": frozenset(
        {
            Permission.WORKSPACE_READ.value,
            Permission.DOCUMENT_READ.value,
            Permission.SESSION_READ.value,
            Permission.SESSION_CREATE.value,
            Permission.SESSION_UPDATE.value,
            Permission.SESSION_DELETE.value,
            Permission.MESSAGE_SEND.value,
        }
    ),
}

# Alias for backward compatibility
ROLE_PERMISSIONS = BUILTIN_ROLE_PERMISSIONS


def get_permissions_for_role(role: str | None) -> frozenset[str]:
    """Resolve permissions for a given role (backward compatibility)."""
    return effective_permissions(role)


def effective_permissions(
    role: str | None,
    stored_permissions: set[str] | frozenset[str] | None = None,
) -> frozenset[str]:
    """Compute effective permissions at read time (Vishop architecture).

    - If role is 'owner', bypass all checks and return all catalog permissions plus wildcard '*'.
    - For other roles, merge built-in role permissions with any custom stored permissions.
    """
    if not role:
        return frozenset()

    clean_role = role.strip().lower()
    if clean_role == "owner":
        return frozenset(ALL_PERMISSION_CODES | {"*"})

    base = BUILTIN_ROLE_PERMISSIONS.get(clean_role, frozenset())
    if stored_permissions:
        return frozenset(base | set(stored_permissions))
    return base


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

    def has_permission(self, permission: str | Permission) -> bool:
        """Check if principal possesses a specific permission or wildcard access."""
        if self.is_owner:
            return True
        perm_key = permission.value if isinstance(permission, Permission) else str(permission)
        return "*" in self.permissions or perm_key in self.permissions

    def has_any_permission(self, *permissions: str | Permission) -> bool:
        """Check if principal possesses at least one of the specified permissions (OR check)."""
        if self.is_owner:
            return True
        return any(self.has_permission(p) for p in permissions)

    def has_all_permissions(self, *permissions: str | Permission) -> bool:
        """Check if principal possesses all of the specified permissions (AND check)."""
        if self.is_owner:
            return True
        return all(self.has_permission(p) for p in permissions)

    def has_role(self, *roles: str) -> bool:
        """Check if principal matches any of the specified roles."""
        return self.role in roles

    def require_permission(self, *permissions: str | Permission) -> None:
        """Assert that caller possesses ALL listed permissions (AND check).

        Raises ForbiddenException (403) if any permission is missing.
        """
        if self.is_owner:
            return
        for perm in permissions:
            if not self.has_permission(perm):
                perm_key = perm.value if isinstance(perm, Permission) else str(perm)
                raise ForbiddenException(f"Missing required permission: '{perm_key}'")

    def require_any_permission(self, *permissions: str | Permission) -> None:
        """Assert that caller possesses AT LEAST ONE of the listed permissions (OR check).

        Raises ForbiddenException (403) if none of the permissions are granted.
        """
        if self.is_owner:
            return
        if not self.has_any_permission(*permissions):
            keys = ", ".join(p.value if isinstance(p, Permission) else str(p) for p in permissions)
            raise ForbiddenException(f"Missing required permission. Requires at least one of: [{keys}]")

    def require_role(self, *roles: str) -> None:
        """Assert that caller has one of the specified roles.

        Raises ForbiddenException (403) if role does not match.
        """
        if not self.has_role(*roles):
            raise ForbiddenException(f"User requires one of roles: {roles}, but has '{self.role}'")


@dataclass(frozen=True)
class ExecutionContext:
    principal: CurrentPrincipal | None = None
    request_id: str | None = None


def require_workspace_member(
    uow: UnitOfWork,
    principal: CurrentPrincipal,
    workspace_id: uuid.UUID,
) -> None:
    workspace = uow.workspaces.get_by_id(workspace_id)
    if workspace is None or not workspace.is_member(principal.user_id):
        raise ForbiddenException("User is not a member of this workspace.")


def require_document_access(
    uow: UnitOfWork,
    principal: CurrentPrincipal,
    document_id: uuid.UUID,
    permission: str | Permission | None = None,
) -> None:
    document = uow.documents.get_by_id(document_id)
    if document is None:
        raise ForbiddenException("User cannot access this document.")
    require_workspace_member(uow, principal, document.workspace_id)
    if permission is not None:
        require_workspace_permission(uow, principal, document.workspace_id, permission)


def require_session_access(
    uow: UnitOfWork,
    principal: CurrentPrincipal,
    session_id: uuid.UUID,
    permission: str | Permission | None = None,
) -> None:
    session = uow.sessions.get_by_id(session_id)
    if session is None:
        raise ForbiddenException("User cannot access this chat session.")
    require_workspace_member(uow, principal, session.workspace_id)
    if permission is not None:
        require_workspace_permission(uow, principal, session.workspace_id, permission)


def require_workspace_permission(
    uow: UnitOfWork,
    principal: CurrentPrincipal,
    workspace_id: uuid.UUID,
    permission: str | Permission,
) -> None:
    """Ensure principal is a member of workspace and holds the required permission."""
    require_workspace_member(uow, principal, workspace_id)

    if principal.is_owner and principal.active_workspace_id == workspace_id:
        return

    if principal.active_workspace_id == workspace_id:
        principal.require_permission(permission)
        return

    role = uow.workspaces.get_member_role(workspace_id, principal.user_id)
    if role and role.strip().lower() == "owner":
        return

    perm_key = permission.value if isinstance(permission, Permission) else str(permission)
    if not uow.workspaces.has_permission(workspace_id, principal.user_id, perm_key):
        raise ForbiddenException(f"Missing required permission: '{perm_key}' in workspace.")

