"""Presentation router for workspaces and permission catalog."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends

from chat_api.modules.workspaces.presentation.dtos import (
    PermissionCatalogResponse,
    PermissionGroupResponse,
    PermissionItemResponse,
)
from chat_api.shared.auth import PERMISSION_CATALOG, CurrentAuth, RequireAuth, auth_openapi

router = APIRouter(tags=["workspaces"])


@router.get(
    "/workspaces/permissions/catalog",
    response_model=PermissionCatalogResponse,
    dependencies=[Depends(RequireAuth())],
    openapi_extra=auth_openapi(),
)
@router.get(
    "/permissions/catalog",
    response_model=PermissionCatalogResponse,
    dependencies=[Depends(RequireAuth())],
    openapi_extra=auth_openapi(),
)
def get_permission_catalog(auth: CurrentAuth) -> PermissionCatalogResponse:
    """Return the entire permission catalog grouped by module.

    Any authenticated user session can retrieve this catalog to render
    role matrix and permission configurations.
    """
    groups_map: dict[str, list[PermissionItemResponse]] = defaultdict(list)
    for item in PERMISSION_CATALOG:
        groups_map[item.module].append(
            PermissionItemResponse(
                code=item.code,
                name=item.name,
                description=item.description,
                module=item.module,
            )
        )

    groups = [
        PermissionGroupResponse(module=mod, permissions=perms) for mod, perms in groups_map.items()
    ]
    return PermissionCatalogResponse(
        groups=groups,
        total=len(PERMISSION_CATALOG),
    )
