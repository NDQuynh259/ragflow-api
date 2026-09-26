"""Reports and Analytics presentation router (Composition Layer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from chat_api.composition.reports.application.dtos import (
    WorkspaceDailyActivityResponse,
    WorkspaceOverviewReportResponse,
)
from chat_api.composition.reports.application.services import ReportService
from chat_api.shared.auth import (
    CurrentAuth,
    Permission,
    RequireAuth,
    RequirePermission,
    auth_openapi,
)
from core.database import get_db

router = APIRouter(
    prefix="/reports",
    tags=["Reports & Analytics (Composition)"],
    dependencies=[Depends(RequireAuth())],
)


def get_report_service(db: Session = Depends(get_db)) -> ReportService:
    """Dependency provider for ReportService."""
    return ReportService(db)


# region get_workspace_overview_report
@router.get(
    "/overview",
    response_model=WorkspaceOverviewReportResponse,
    summary="Báo cáo tổng quan không gian làm việc (Multi-table Overview)",
    description="Tổng hợp chỉ số đa bảng (Workspace, Members, Documents, Chunks, Sessions, Messages, Tokens, Feedback).",
    dependencies=[Depends(RequirePermission(Permission.REPORT_READ))],
    openapi_extra=auth_openapi(Permission.REPORT_READ),
)
def get_workspace_overview_report(
    auth: CurrentAuth,
    report_service: ReportService = Depends(get_report_service),
) -> WorkspaceOverviewReportResponse:
    return report_service.get_workspace_overview(auth.active_workspace_id)


# endregion


# region get_workspace_daily_activity_report
@router.get(
    "/activity",
    response_model=WorkspaceDailyActivityResponse,
    summary="Báo cáo xu hướng hoạt động theo ngày",
    description="Thống kê số lượng upload tài liệu, tin nhắn và phiên hội thoại mới trong N ngày gần nhất.",
    dependencies=[Depends(RequirePermission(Permission.REPORT_READ))],
    openapi_extra=auth_openapi(Permission.REPORT_READ),
)
def get_workspace_daily_activity_report(
    auth: CurrentAuth,
    days: int = Query(30, ge=1, le=90, description="Số ngày cần thống kê (1 - 90 ngày)"),
    report_service: ReportService = Depends(get_report_service),
) -> WorkspaceDailyActivityResponse:
    return report_service.get_workspace_daily_activity(auth.active_workspace_id, days=days)


# endregion
