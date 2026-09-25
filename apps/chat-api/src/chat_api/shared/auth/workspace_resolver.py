"""S                        ervice for resolving target workspace context from HTTP requests."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from chat_api.shared.auth.guards import AuthContext


class WorkspaceResolutionService:
    """Encapsulates the resolution of the target workspace ID from HTTP requests, entities, or session defaults."""

    @staticmethod
    async def resolve_workspace_id(
        request: Request | None,
        auth: AuthContext,
    ) -> uuid.UUID | None:
        """Resolve target workspace ID from path parameter, header, query parameter, body, or session."""
        if request is None:
            return auth.principal.active_workspace_id or auth.session.active_workspace_id

        # 1. Direct workspace_id in path parameters (/workspaces/{workspace_id}/...)
        ws_param = request.path_params.get("workspace_id")
        if ws_param:
            try:
                return uuid.UUID(str(ws_param))
            except ValueError:
                pass

        # 2. Workspace ID in header (X-Workspace-Id)
        ws_header = request.headers.get("X-Workspace-Id")
        if ws_header:
            try:
                return uuid.UUID(ws_header.strip())
            except ValueError:
                pass

        # 3. Query parameter (?workspace_id=...)
        ws_query = request.query_params.get("workspace_id")
        if ws_query:
            try:
                return uuid.UUID(ws_query.strip())
            except ValueError:
                pass

        # 4. Resolve from document_id in path if present
        doc_param = request.path_params.get("document_id")
        if doc_param and auth.uow:
            try:
                doc = auth.uow.documents.get_by_id(uuid.UUID(str(doc_param)))
                if doc:
                    return doc.workspace_id
            except (ValueError, AttributeError):
                pass

        # 5. Resolve from session_id in path if present
        session_param = request.path_params.get("session_id")
        if session_param and auth.uow:
            try:
                s = auth.uow.chat_sessions.get_by_id(uuid.UUID(str(session_param)))
                if s:
                    return s.workspace_id
            except (ValueError, AttributeError):
                pass

        # 6. Resolve from JSON request body if present (e.g. POST /chat-sessions {"workspace_id": ...})
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_json = json.loads(body_bytes)
                    if isinstance(body_json, dict) and "workspace_id" in body_json:
                        return uuid.UUID(str(body_json["workspace_id"]))
            except Exception:
                pass

        # 7. Fall back to current active workspace in session
        return auth.principal.active_workspace_id or auth.session.active_workspace_id


__all__ = ["WorkspaceResolutionService"]
