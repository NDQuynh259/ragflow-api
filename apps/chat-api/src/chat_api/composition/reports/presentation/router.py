"""Reports and Analytics presentation router (Composition Layer)."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from chat_api.composition.reports.application.dtos import (
    WorkspaceDailyActivityResponse,
    WorkspaceOverviewReportResponse,
)
from chat_api.composition.reports.application.services import ReportService
from chat_api.modules.auth.presentation.dependencies import (
    AuthDep,
    RequirePermission,
    auth_openapi,
)
from chat_api.shared.application.authorization import Permission
from chat_api.shared.infrastructure.database.session import get_db
from core.exceptions import ForbiddenException

router = APIRouter(prefix="/reports", tags=["Reports & Analytics (Composition)"])


def get_report_service(db: Session = Depends(get_db)) -> ReportService:
    """Dependency provider for ReportService."""
    return ReportService(db)


@router.get(
    "/overview",
    response_model=WorkspaceOverviewReportResponse,
    summary="Báo cáo tổng quan không gian làm việc (Multi-table Overview)",
    description="Tổng hợp chỉ số đa bảng (Workspace, Members, Documents, Chunks, Sessions, Messages, Tokens, Feedback).",
    dependencies=[Depends(RequirePermission(Permission.REPORT_READ))],
    openapi_extra=auth_openapi(Permission.REPORT_READ),
)
def get_workspace_overview_report(
    auth: AuthDep,
    workspace_id: uuid.UUID | None = Query(
        None,
        description="Tùy chọn Workspace ID cần xem báo cáo. Mặc định là active workspace của phiên làm việc.",
    ),
    report_service: ReportService = Depends(get_report_service),
) -> WorkspaceOverviewReportResponse:
    target_workspace_id = (
        workspace_id
        or auth.principal.active_workspace_id
        or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException("Active workspace is not set. Please switch or select an active workspace.")

    return report_service.get_workspace_overview(target_workspace_id)


@router.get(
    "/activity",
    response_model=WorkspaceDailyActivityResponse,
    summary="Báo cáo xu hướng hoạt động theo ngày",
    description="Thống kê số lượng upload tài liệu, tin nhắn và phiên hội thoại mới trong N ngày gần nhất.",
    dependencies=[Depends(RequirePermission(Permission.REPORT_READ))],
    openapi_extra=auth_openapi(Permission.REPORT_READ),
)
def get_workspace_daily_activity_report(
    auth: AuthDep,
    workspace_id: uuid.UUID | None = Query(
        None,
        description="Tùy chọn Workspace ID cần xem báo cáo. Mặc định là active workspace của phiên làm việc.",
    ),
    days: int = Query(30, ge=1, le=90, description="Số ngày cần thống kê (1 - 90 ngày)"),
    report_service: ReportService = Depends(get_report_service),
) -> WorkspaceDailyActivityResponse:
    target_workspace_id = (
        workspace_id
        or auth.principal.active_workspace_id
        or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException("Active workspace is not set. Please switch or select an active workspace.")

    return report_service.get_workspace_daily_activity(target_workspace_id, days=days)
