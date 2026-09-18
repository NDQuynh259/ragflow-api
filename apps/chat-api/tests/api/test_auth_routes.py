"""Integration tests for Authentication API routes."""

from fastapi.testclient import TestClient
from chat_api.main import app
from chat_api.shared.infrastructure.database import UnitOfWork, get_uow


def test_auth_full_session_flow(fake_uow):
    app.dependency_overrides[get_uow] = lambda: fake_uow
    client = TestClient(app, base_url="https://testserver")

    try:
        # 1. Register
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "email": "sarah@example.com",
                "password": "strongPassword123",
                "full_name": "Sarah Connor",
            },
        )
        assert reg_res.status_code == 201
        data = reg_res.json()
        assert data["email"] == "sarah@example.com"
        assert data["full_name"] == "Sarah Connor"

        # 2. Login
        login_res = client.post(
            "/api/v1/auth/login",
            json={
                "email": "sarah@example.com",
                "password": "strongPassword123",
            },
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert "session_token" in login_data
        assert login_data["active_workspace_id"] is not None
        initial_ws_id = login_data["active_workspace_id"]
        session_token = login_data["session_token"]

        # Check Set-Cookie header is present
        set_cookie = login_res.headers.get("set-cookie", "")
        assert "session_token=" in set_cookie
        assert "HttpOnly" in set_cookie

        # 3. GET /me via Cookie (TestClient automatically stores and sends cookies)
        me_cookie_res = client.get("/api/v1/auth/me")
        assert me_cookie_res.status_code == 200
        me_data = me_cookie_res.json()
        assert me_data["email"] == "sarah@example.com"
        assert me_data["active_workspace_id"] == initial_ws_id
        assert len(me_data["workspaces"]) == 1
        assert me_data["workspaces"][0]["role"] == "owner"
        assert "documents:create" in me_data["workspaces"][0]["permissions"]

        # 4. GET /me via Bearer Token header (Scalar / Postman style)
        clean_client = TestClient(app, base_url="https://testserver")
        unauth_res = clean_client.get("/api/v1/auth/me")
        assert unauth_res.status_code == 401

        bearer_res = clean_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert bearer_res.status_code == 200
        assert bearer_res.json()["email"] == "sarah@example.com"

        # 5. Switch Workspace
        import uuid
        from chat_api.modules.workspaces.domain.entity import Workspace, WorkspaceMember, WorkspaceRole
        second_ws = Workspace(
            name="Secondary Team Workspace",
            slug="secondary-team",
            members=[
                WorkspaceMember(
                    workspace_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    user_id=uuid.UUID(me_data["id"]),
                    role=WorkspaceRole.ADMIN,
                )
            ],
        )
        second_ws.members[0].workspace_id = second_ws.id
        fake_uow.workspaces.save(second_ws)

        switch_res = client.post(
            "/api/v1/auth/switch-workspace",
            json={"workspace_id": str(second_ws.id)},
        )
        assert switch_res.status_code == 200
        assert switch_res.json()["active_workspace_id"] == str(second_ws.id)

        # Verify /me now reflects the switched workspace and 2 workspaces
        me_updated = client.get("/api/v1/auth/me").json()
        assert me_updated["active_workspace_id"] == str(second_ws.id)
        assert len(me_updated["workspaces"]) == 2

        # 6. Logout
        logout_res = client.post("/api/v1/auth/logout")
        assert logout_res.status_code == 200
        assert "logged out" in logout_res.json()["message"].lower()

        # 7. GET /me after logout fails
        after_logout_res = client.get("/api/v1/auth/me")
        assert after_logout_res.status_code == 401

    finally:
        app.dependency_overrides.clear()
