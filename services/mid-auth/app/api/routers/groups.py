"""Platform group chat API (VoceChat-backed)."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.chat import (
    ChatMessageCreateRequest,
    ChatMessageOperationResponse,
    LastMessageReadRequest,
    MessageLikeRequest,
    MessageListResponse,
    MessageOut,
)
from app.schemas.groups import (
    ChangeGroupTypeRequest,
    GroupCreateRequest,
    GroupCreateResponse,
    GroupListResponse,
    GroupMembersAddRequest,
    GroupOut,
    GroupPinMessageRequest,
    GroupRealtimeTokenResponse,
    GroupUpdateRequest,
)
from app.services.chat_service import ChatServiceError
from app.services.group_service import group_message_main_mime, group_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _op_mid(mid: int) -> ChatMessageOperationResponse:
    return ChatMessageOperationResponse(message_id=str(int(mid)))


@router.get("/me/groups", response_model=GroupListResponse)
def list_my_groups(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    public_only: bool | None = Query(None),
) -> GroupListResponse:
    try:
        return group_service.list_groups(
            db, current_user, vc, public_only=public_only
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups", response_model=GroupCreateResponse, status_code=201)
def create_group(
    payload: GroupCreateRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupCreateResponse:
    try:
        return group_service.create_group(db, current_user, vc, payload)
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/groups/{group_id}", response_model=GroupOut)
def get_group(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupOut:
    try:
        return group_service.get_group(db, current_user, vc, group_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/groups/{group_id}/realtime-token",
    response_model=GroupRealtimeTokenResponse,
)
def get_group_realtime_token(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupRealtimeTokenResponse:
    """Return a short-lived token and channel info for group voice/video (VoceChat-backed)."""
    try:
        return group_service.get_realtime_token(db, current_user, vc, group_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/avatar", status_code=204)
async def upload_group_avatar(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
) -> None:
    """Upload group avatar (VoceChat ``POST /group/{gid}/avatar``, PNG body)."""
    raw = await file.read()
    ct_main = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    png_magic = len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n"
    if ct_main != "image/png" and not png_magic:
        raise HTTPException(status_code=400, detail="file must be image/png")
    try:
        group_service.upload_group_avatar(
            db, current_user, vc, group_id, raw
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.patch("/me/groups/{group_id}", status_code=204)
def patch_group(
    group_id: str,
    payload: GroupUpdateRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.update_group(db, current_user, vc, group_id, payload)
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/groups/{group_id}", status_code=204)
def delete_group(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.delete_group(db, current_user, vc, group_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/members", status_code=204)
def add_group_members(
    group_id: str,
    payload: GroupMembersAddRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.add_members(
            db,
            current_user,
            vc,
            group_id,
            payload.target_public_ids,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/groups/{group_id}/members/{target_public_id}", status_code=204)
def remove_group_member(
    group_id: str,
    target_public_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.remove_member(
            db, current_user, vc, group_id, target_public_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/change-type", status_code=204)
def change_group_type(
    group_id: str,
    payload: ChangeGroupTypeRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.change_group_type(db, current_user, vc, group_id, payload)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/leave", status_code=204)
def leave_group(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.leave_group(db, current_user, vc, group_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/read", status_code=204)
def mark_group_read(
    group_id: str,
    payload: LastMessageReadRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.mark_group_read(
            db,
            current_user,
            vc,
            group_id,
            payload.last_message_id,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/pin", status_code=204)
def pin_group_message(
    group_id: str,
    payload: GroupPinMessageRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.pin_message(
            db, current_user, vc, group_id, payload.message_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/groups/{group_id}/unpin", status_code=204)
def unpin_group_message(
    group_id: str,
    payload: GroupPinMessageRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        group_service.unpin_message(
            db, current_user, vc, group_id, payload.message_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/groups/{group_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
async def send_group_message(
    group_id: str,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    """Send a group message: ``application/json`` ``{body}`` or VoceChat raw types."""
    ct_header = request.headers.get("content-type") or ""
    body = await request.body()
    mime = group_message_main_mime(ct_header)
    if mime == "application/json":
        try:
            payload = ChatMessageCreateRequest.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        try:
            return group_service.send_message(
                db, current_user, vc, group_id, payload.body
            )
        except ChatServiceError as exc:
            _handle(exc)
    x_prop = request.headers.get("X-Properties") or request.headers.get(
        "x-properties"
    )
    x_prop_n = x_prop.strip() if x_prop else None
    try:
        return group_service.send_message_voce_payload(
            db,
            current_user,
            vc,
            group_id,
            raw_body=body,
            content_type_header=ct_header,
            x_properties=x_prop_n,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.put(
    "/me/groups/{group_id}/messages/{message_id}/edit",
    response_model=ChatMessageOperationResponse,
)
async def edit_group_message(
    group_id: str,
    message_id: str,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    ct_header = request.headers.get("content-type") or ""
    mime = group_message_main_mime(ct_header)
    x_prop = request.headers.get("X-Properties") or request.headers.get(
        "x-properties"
    )
    x_prop_n = x_prop.strip() if x_prop else None
    try:
        if mime == "application/json":
            body = await request.json()
            payload = ChatMessageCreateRequest.model_validate(body)
            mid = group_service.edit_group_message(
                db,
                current_user,
                vc,
                group_id,
                message_id,
                json_text=payload.body,
                x_properties=x_prop_n,
            )
            return _op_mid(mid)
        raw = await request.body()
        mid = group_service.edit_group_message(
            db,
            current_user,
            vc,
            group_id,
            message_id,
            raw_body=raw,
            content_type_header=ct_header,
            x_properties=x_prop_n,
        )
        return _op_mid(mid)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ChatServiceError as exc:
        _handle(exc)


@router.put(
    "/me/groups/{group_id}/messages/{message_id}/like",
    response_model=ChatMessageOperationResponse,
)
def like_group_message(
    group_id: str,
    message_id: str,
    payload: MessageLikeRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    try:
        mid = group_service.like_group_message(
            db,
            current_user,
            vc,
            group_id,
            message_id,
            action=payload.action,
        )
        return _op_mid(mid)
    except ChatServiceError as exc:
        _handle(exc)


@router.delete(
    "/me/groups/{group_id}/messages/{message_id}",
    response_model=ChatMessageOperationResponse,
)
def delete_group_message(
    group_id: str,
    message_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    try:
        mid = group_service.delete_group_message(
            db, current_user, vc, group_id, message_id
        )
        return _op_mid(mid)
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/groups/{group_id}/messages/{message_id}/reply",
    response_model=ChatMessageOperationResponse,
)
async def reply_group_message(
    group_id: str,
    message_id: str,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    ct_header = request.headers.get("content-type") or ""
    mime = group_message_main_mime(ct_header)
    x_prop = request.headers.get("X-Properties") or request.headers.get(
        "x-properties"
    )
    x_prop_n = x_prop.strip() if x_prop else None
    try:
        if mime == "application/json":
            body = await request.json()
            payload = ChatMessageCreateRequest.model_validate(body)
            mid = group_service.reply_group_message(
                db,
                current_user,
                vc,
                group_id,
                message_id,
                json_text=payload.body,
                x_properties=x_prop_n,
            )
            return _op_mid(mid)
        raw = await request.body()
        mid = group_service.reply_group_message(
            db,
            current_user,
            vc,
            group_id,
            message_id,
            raw_body=raw,
            content_type_header=ct_header,
            x_properties=x_prop_n,
        )
        return _op_mid(mid)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/groups/{group_id}/messages",
    response_model=MessageListResponse,
)
def list_group_messages(
    group_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    before_message_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=300),
) -> MessageListResponse:
    try:
        return group_service.list_messages(
            db,
            current_user,
            vc,
            group_id,
            before_message_id=before_message_id,
            limit=limit,
        )
    except ChatServiceError as exc:
        _handle(exc)
