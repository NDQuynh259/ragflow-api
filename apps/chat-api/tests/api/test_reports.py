"""API integration tests for Reports & Analytics Composition endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from fastapi.testclient import TestClient

from chat_api.composition.reports.application.dtos import (
    ChatStatsDTO,
    DailyActivityItemDTO,
    DocumentStatsDTO,
    MemberStatsDTO,
    WorkspaceDailyActivityResponse,
    WorkspaceOverviewReportResponse,
)
from chat_api.composition.reports.application.services import ReportService
from chat_api.composition.reports.presentation.router import get_report_service
from chat_api.main import app
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.presentation.dependencies import AuthContext, get_auth_context
from chat_api.modules.users.domain.entity import User
from chat_api.shared.application.authorization import CurrentPrincipal, ExecutionContext, Permission
from chat_api.shared.application.bus import CommandBus, QueryBus
from chat_api.shared.infrastructure.database.uow import get_uow


class MockReportService:
    """Mock implementation of ReportService for isolated API tests."""

    def __init__(self, workspace_id: uuid.UUID) -> None:
        self.workspace_id = workspace_id

    def get_workspace_overview(self, workspace_id: uuid.UUID) -> WorkspaceOverviewReportResponse:
        return WorkspaceOverviewReportResponse(
            workspace_id=workspace_id,
            workspace_name="Test Engineering Workspace",
            generated_at=datetime.now(timezone.utc),
            members=MemberStatsDTO(total_members=5),
            documents=DocumentStatsDTO(
                total_documents=12,
                total_file_size_bytes=1048576,
                total_pages=45,
                ready_documents=10,
                failed_documents=1,
                processing_documents=1,
                total_chunks=150,
            ),
            chat=ChatStatsDTO(
                total_sessions=20,
                total_messages=80,
                user_messages=40,
                assistant_messages=40,
                total_prompt_tokens=5000,
                total_completion_tokens=3000,
                total_citations=35,
                average_latency_ms=420.5,
                total_feedbacks=10,
                positive_feedbacks=8,
                negative_feedbacks=2,
            ),
        )

    def get_workspace_daily_activity(
        self, workspace_id: uuid.UUID, days: int = 30
    ) -> WorkspaceDailyActivityResponse:
        return WorkspaceDailyActivityResponse(
            workspace_id=workspace_id,
            days=days,
            activities=[
                DailyActivityItemDTO(
                    date="2026-09-15",
                    documents_uploaded=2,
                    messages_sent=15,
                    sessions_created=3,
                ),
                DailyActivityItemDTO(
                    date="2026-09-16",
                    documents_uploaded=4,
                    messages_sent=25,
                    sessions_created=5,
                ),
            ],
        )


from chat_api.modules.workspaces.domain.entity import Workspace, WorkspaceMember, WorkspaceRole


@pytest.fixture
def auth_client_with_reports(fake_uow):
    ws_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), email="admin@example.com", full_name="Workspace Admin")
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token="valid-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    principal = CurrentPrincipal(
        user_id=user.id,
        session_id=session.id,
        active_workspace_id=ws_id,
        role="owner",
        permissions=frozenset({
            Permission.WORKSPACE_READ.value,
            Permission.REPORT_READ.value,
        }),
    )
    execution = ExecutionContext(principal=principal)

    # Register workspace & membership in fake_uow
    ws = Workspace(
        id=ws_id,
        name="Test Engineering Workspace",
        slug="test-workspace",
        members=[
            WorkspaceMember(
                workspace_id=ws_id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            )
        ],
    )
    fake_uow.workspaces.save(ws)

    mock_service = MockReportService(workspace_id=ws_id)

    app.dependency_overrides[get_uow] = lambda: fake_uow
    app.dependency_overrides[get_report_service] = lambda: mock_service
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=user,
        session=session,
        principal=principal,
        command_bus=CommandBus(fake_uow, execution_context=execution),
        query_bus=QueryBus(fake_uow, execution_context=execution),
        uow=fake_uow,
    )
    yield TestClient(app), ws_id
    app.dependency_overrides.clear()


def test_reports_overview_requires_auth():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get("/api/v1/reports/overview")
    assert resp.status_code == 401


def test_get_workspace_overview_report(auth_client_with_reports):
    client, ws_id = auth_client_with_reports
    resp = client.get(f"/api/v1/reports/overview?workspace_id={ws_id}")
    assert resp.status_code == 200

    data = resp.json()
    assert data["workspace_id"] == str(ws_id)
    assert data["workspace_name"] == "Test Engineering Workspace"

    # Multi-table metrics verification
    assert data["members"]["total_members"] == 5
    assert data["documents"]["total_documents"] == 12
    assert data["documents"]["total_chunks"] == 150
    assert data["chat"]["total_messages"] == 80
    assert data["chat"]["positive_feedbacks"] == 8


def test_get_workspace_daily_activity(auth_client_with_reports):
    client, ws_id = auth_client_with_reports
    resp = client.get(f"/api/v1/reports/activity?workspace_id={ws_id}&days=7")
    assert resp.status_code == 200

    data = resp.json()
    assert data["workspace_id"] == str(ws_id)
    assert data["days"] == 7
    assert len(data["activities"]) == 2
    assert data["activities"][0]["date"] == "2026-09-15"
    assert data["activities"][0]["messages_sent"] == 15
