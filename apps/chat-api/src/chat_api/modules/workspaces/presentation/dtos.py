"""Presentation DTOs for Workspaces and Permission Catalog."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PermissionItemResponse(BaseModel):
    code: str
    name: str
    description: str
    module: str


class PermissionGroupResponse(BaseModel):
    module: str
    permissions: list[PermissionItemResponse] = Field(default_factory=list)


class PermissionCatalogResponse(BaseModel):
    groups: list[PermissionGroupResponse] = Field(default_factory=list)
    total: int = 0
