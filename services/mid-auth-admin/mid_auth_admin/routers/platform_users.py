from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from mid_auth_admin.schemas.platform_users import (
    PlatformName,
    PlatformUserCreateRequest,
    PlatformUserListResponse,
    PlatformUserPatchRequest,
    PlatformUserRecord,
)
from mid_auth_admin.services.platform_user_admin_service import (
    PlatformUserAdminService,
    get_platform_user_admin_service,
)

router = APIRouter()


@router.get("/platform-users/{platform}", response_model=PlatformUserListResponse)
def list_platform_users(
    platform: PlatformName,
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PlatformUserAdminService = Depends(get_platform_user_admin_service),
) -> PlatformUserListResponse:
    return service.list_users(platform=platform, q=q, limit=limit, offset=offset)


@router.get("/platform-users/{platform}/{user_id}", response_model=PlatformUserRecord)
def get_platform_user(
    platform: PlatformName,
    user_id: str,
    service: PlatformUserAdminService = Depends(get_platform_user_admin_service),
) -> PlatformUserRecord:
    return service.get_user(platform=platform, user_id=user_id)


@router.post(
    "/platform-users/{platform}",
    response_model=PlatformUserRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_platform_user(
    platform: PlatformName,
    payload: PlatformUserCreateRequest,
    service: PlatformUserAdminService = Depends(get_platform_user_admin_service),
) -> PlatformUserRecord:
    return service.create_user(platform=platform, payload=payload)


@router.patch("/platform-users/{platform}/{user_id}", response_model=PlatformUserRecord)
def patch_platform_user(
    platform: PlatformName,
    user_id: str,
    payload: PlatformUserPatchRequest,
    service: PlatformUserAdminService = Depends(get_platform_user_admin_service),
) -> PlatformUserRecord:
    return service.update_user(platform=platform, user_id=user_id, payload=payload)


@router.delete("/platform-users/{platform}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_platform_user(
    platform: PlatformName,
    user_id: str,
    service: PlatformUserAdminService = Depends(get_platform_user_admin_service),
) -> Response:
    service.delete_user(platform=platform, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

