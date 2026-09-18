"""Application service for reports and analytics composition."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from chat_api.composition.reports.application.dtos import (
    DailyActivityItemDTO,
    WorkspaceDailyActivityResponse,
    WorkspaceOverviewReportResponse,
)
from chat_api.composition.reports.infrastructure.queries import ReportQueryRepository
from core.exceptions import EntityNotFoundException


class ReportService:
    """Coordinates multi-table reporting queries and maps them to presentation DTOs."""

    def __init__(self, session: Session) -> None:
        self.repo = ReportQueryRepository(session)

    def get_workspace_overview(self, workspace_id: uuid.UUID) -> WorkspaceOverviewReportResponse:
        """Fetch full workspace overview statistics."""
        stats = self.repo.get_workspace_overview(workspace_id)
        if stats is None:
            raise EntityNotFoundException("Workspace", workspace_id)
        return WorkspaceOverviewReportResponse.model_validate(stats)

    def get_workspace_daily_activity(
        self, workspace_id: uuid.UUID, days: int = 30
    ) -> WorkspaceDailyActivityResponse:
        """Fetch daily trend activity points for a workspace."""
        stats = self.repo.get_workspace_overview(workspace_id)
        if stats is None:
            raise EntityNotFoundException("Workspace", workspace_id)
        activities_data = self.repo.get_daily_activity(workspace_id, days=days)
        activities = [DailyActivityItemDTO.model_validate(item) for item in activities_data]
        return WorkspaceDailyActivityResponse(
            workspace_id=workspace_id,
            days=days,
            activities=activities,
        )
