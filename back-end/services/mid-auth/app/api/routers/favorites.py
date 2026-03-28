"""VoceChat favorite archives and attachment download (acting user)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.favorites import (
    CreateFavoriteBody,
    FavoriteArchiveOut,
    FavoriteListResponse,
)
from app.services.chat_service import ChatServiceError, chat_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/im/favorites", response_model=FavoriteListResponse)
def list_my_favorites(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FavoriteListResponse:
    try:
        return chat_service.list_favorite_archives(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/im/favorites",
    response_model=FavoriteArchiveOut,
    status_code=201,
)
def create_my_favorite(
    payload: CreateFavoriteBody,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FavoriteArchiveOut:
    try:
        return chat_service.create_favorite_archive(
            db, current_user, vc, payload
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/favorites/{favorite_id}")
def get_my_favorite_archive(
    favorite_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return chat_service.get_favorite_archive_detail(
            db, current_user, vc, favorite_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/im/favorites/{favorite_id}", status_code=204)
def delete_my_favorite(
    favorite_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        chat_service.delete_favorite_archive(
            db, current_user, vc, favorite_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/favorites/{favorite_id}/attachments/{attachment_id}")
def download_favorite_attachment(
    favorite_id: str,
    attachment_id: int,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    download: bool = Query(False),
) -> Response:
    try:
        body, content_type, content_disposition = (
            chat_service.download_favorite_attachment(
                db,
                current_user,
                vc,
                favorite_id,
                attachment_id,
                download=download,
            )
        )
    except ChatServiceError as exc:
        _handle(exc)
    headers: dict[str, str] = {}
    if content_disposition:
        headers["Content-Disposition"] = content_disposition
    media = (content_type or "").strip() or "application/octet-stream"
    return Response(content=body, media_type=media, headers=headers)
