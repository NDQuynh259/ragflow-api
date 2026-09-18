"""Authentication DTOs (Data Transfer Objects)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 characters)")
    full_name: str | None = Field(None, description="User display name")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    is_active: bool
    created_at: datetime


class WorkspaceInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    role: str = "member"
    permissions: list[str] = Field(default_factory=list)


class UserMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    is_active: bool
    created_at: datetime
    active_workspace_id: uuid.UUID | None = None
    workspaces: list[WorkspaceInfo] = Field(default_factory=list)


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: uuid.UUID = Field(..., description="Target workspace ID to switch active context")


class SwitchWorkspaceResponse(BaseModel):
    active_workspace_id: uuid.UUID
    message: str = "Active workspace switched successfully."


class AuthResponse(BaseModel):
    user: UserResponse
    active_workspace_id: uuid.UUID | None = None
    session_token: str
    expires_at: datetime


class MessageResponse(BaseModel):
    message: str
