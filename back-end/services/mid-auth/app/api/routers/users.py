"""Platform user directory (public_id lookup; safe fields only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.db.session import get_db
from app.models.users import User
from app.schemas.directory import (
    UserDirectoryLookupRequest,
    UserDirectorySearchListResponse,
    UserDirectorySearchRequest,
    UserDirectorySearchResult,
)
from app.services.chat_service import ChatServiceError
from app.services.profile_service import ProfileService
from app.services.social_service import social_service

router = APIRouter()
_profile = ProfileService()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post(
    "/me/directory/users/lookup",
    response_model=UserDirectorySearchResult,
    summary="Look up a user by platform public_id",
)
def lookup_directory_user(
    payload: UserDirectoryLookupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserDirectorySearchResult:
    try:
        return social_service.lookup_directory_user_by_public_id(
            db, current_user, public_id=payload.public_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/directory/users/search",
    response_model=UserDirectorySearchListResponse,
    summary="Search users by username/email/public_id",
)
def search_directory_users(
    payload: UserDirectorySearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserDirectorySearchListResponse:
    try:
        items = social_service.search_directory_users(
            db,
            current_user,
            keyword=payload.keyword,
            limit=payload.limit,
        )
        return UserDirectorySearchListResponse(items=items)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/directory/users/{public_id}/avatar",
    summary="Get user's avatar by platform public_id",
)
def get_directory_user_avatar(
    public_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Response:
    target = db.query(User).filter(User.public_id == public_id.strip()).first()
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    payload = _profile.get_avatar_payload(target)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no avatar")
    data, mime = payload
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )
