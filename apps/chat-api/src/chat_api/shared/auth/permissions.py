"""Authorization primitives and permission catalog (inspired by ViShop architecture)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import ForbiddenException
from core.security import CurrentPrincipal, ExecutionContext


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

    # Reports & Analytics (Composition)
    REPORT_READ = "reports:read"


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
    PermissionItem(
        code=Permission.REPORT_READ.value,
        name="Xem báo cáo và thống kê",
        description="Xem số liệu tổng hợp, phân tích đa bảng của không gian làm việc",
        module="reports",
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
            Permission.REPORT_READ.value,
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
            Permission.REPORT_READ.value,
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
    stored_permissions: Iterable[str] | None = None,
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
    session = uow.chat_sessions.get_by_id(session_id)
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


__all__ = [
    "Permission",
    "PermissionItem",
    "PERMISSION_CATALOG",
    "ALL_PERMISSION_CODES",
    "BUILTIN_ROLE_PERMISSIONS",
    "ROLE_PERMISSIONS",
    "get_permissions_for_role",
    "effective_permissions",
    "CurrentPrincipal",
    "ExecutionContext",
    "require_workspace_member",
    "require_document_access",
    "require_session_access",
    "require_workspace_permission",
]
