"""VoceChat static resource proxies: file download/delete, message archive, OG parse."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.chat_resources import CreateMessageArchiveBody, MessageArchivePathOut
from app.services.chat_service import ChatServiceError, chat_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/im/resources/file")
def get_chat_resource_file(
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file_path: str = Query(..., description="VoceChat storage path (e.g. year/month/day/uuid)"),
    thumbnail: bool = Query(False),
    download: bool = Query(False),
):
    """Proxy ``GET /resource/file`` (bytes, conditional/range headers forwarded)."""
    try:
        return chat_service.proxy_chat_resource_file(
            db,
            current_user,
            vc,
            request,
            file_path=file_path,
            thumbnail=thumbnail,
            download=download,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/im/resources/file", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_resource_file(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file_path: str = Query(..., description="VoceChat storage path to delete"),
) -> None:
    """Proxy ``DELETE /resource/file`` (downstream may return 405 if unsupported)."""
    try:
        chat_service.delete_chat_resource_file(
            db, current_user, vc, file_path=file_path
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/im/resources/archive",
    response_model=MessageArchivePathOut,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_message_archive(
    body: CreateMessageArchiveBody,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageArchivePathOut:
    """Proxy ``POST /resource/archive`` — returns opaque archive ``file_path``."""
    try:
        path = chat_service.create_chat_message_archive(
            db, current_user, vc, body
        )
        return MessageArchivePathOut(file_path=path)
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/resources/archive")
def get_chat_message_archive(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file_path: str = Query(..., description="Archive path from create-archive response"),
) -> dict:
    """Proxy ``GET /resource/archive`` — archive index JSON."""
    try:
        return chat_service.get_chat_message_archive(
            db, current_user, vc, file_path=file_path
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/resources/archive/attachment")
def get_chat_archive_attachment(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file_path: str = Query(...),
    attachment_id: int = Query(..., ge=0),
    download: bool = Query(False),
):
    """Proxy ``GET /resource/archive/attachment``."""
    try:
        return chat_service.proxy_chat_archive_attachment(
            db,
            current_user,
            vc,
            file_path=file_path,
            attachment_id=attachment_id,
            download=download,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/resources/open-graphic")
def get_chat_open_graphic(
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    url: str = Query(..., description="URL to fetch Open Graph metadata for"),
) -> dict:
    """Proxy ``GET /resource/open_graphic_parse``."""
    try:
        return chat_service.get_chat_open_graphic(
            db,
            current_user,
            vc,
            target_url=url,
            accept_language=request.headers.get("accept-language"),
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/resources/group-avatar")
def get_chat_resource_group_avatar(
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    gid: int = Query(..., ge=1, description="VoceChat group id for the avatar image"),
):
    """Proxy ``GET /resource/group_avatar``."""
    try:
        return chat_service.proxy_resource_group_avatar(
            db,
            current_user,
            vc,
            request,
            gid=gid,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/im/resources/organization-logo")
def get_chat_resource_organization_logo(
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    t: int | None = Query(
        None,
        description="Optional cache-busting timestamp (forwarded as VoceChat ``t`` query only)",
    ),
):
    """Proxy ``GET /resource/organization/logo``."""
    try:
        return chat_service.proxy_resource_organization_logo(
            db,
            current_user,
            vc,
            request,
            cache_buster=t,
        )
    except ChatServiceError as exc:
        _handle(exc)
