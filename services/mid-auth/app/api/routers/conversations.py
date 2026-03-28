"""Platform 1:1 conversations API (VoceChat-backed; VoceChat paths not exposed).

See ``app.services.chat_service`` and ``app.schemas.chat`` for v1 semantics:
contacts-based conversation list, ``conversation_id`` = peer VoceChat uid.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.responses import StreamingResponse

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.users import User
from app.schemas.chat import (
    ChatMessageCreateRequest,
    ChatMessageOperationResponse,
    ChatEventsSubscribeParams,
    ChatSessionInvalidateRequest,
    ConversationListResponse,
    LastMessageReadRequest,
    MessageLikeRequest,
    MessageListResponse,
    MessageOut,
    PinUnpinChatRequest,
    StartDirectConversationRequest,
    StartDirectConversationResponse,
    VocechatAccountDeleteRequest,
)
from app.services.group_service import group_message_main_mime
from app.services.chat_service import ChatServiceError, chat_service
from app.services.vocechat_events_proxy import (
    VoceChatEventStreamError,
    VoceChatSseSession,
)

router = APIRouter()

_ConversationIdPath = Annotated[
    str,
    Path(
        description=(
            "v1: peer VoceChat user id (decimal string) for this 1:1 DM. "
            "Not a platform-owned conversation or thread id; same value as the "
            "``id`` field on each row from GET /me/conversations."
        ),
    ),
]


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _chat_events_query(
    after_mid: int | None = Query(None),
    users_version: int | None = Query(None),
) -> ChatEventsSubscribeParams:
    return ChatEventsSubscribeParams(
        after_mid=after_mid, users_version=users_version
    )


@router.get("/me/im/events")
async def subscribe_chat_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    q: ChatEventsSubscribeParams = Depends(_chat_events_query),
) -> StreamingResponse:
    """Subscribe to VoceChat user events via SSE (opaque ``text/event-stream`` body)."""
    settings = get_settings()
    if not settings.vocechat_base_url:
        raise HTTPException(
            status_code=503, detail="vocechat backend is not configured"
        )
    try:
        acting_uid = chat_service.resolve_events_acting_uid(db, current_user)
    except ChatServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc

    try:
        session = await VoceChatSseSession.start(
            request=request,
            settings=settings,
            acting_uid=acting_uid,
            user_id=current_user.id,
            after_mid=q.after_mid,
            users_version=q.users_version,
        )
    except VoceChatEventStreamError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc

    return StreamingResponse(
        session.stream_bytes(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/me/im/session/invalidate", status_code=204)
def invalidate_chat_session(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _body: ChatSessionInvalidateRequest | None = Body(default=None),
) -> None:
    """Invalidate the VoceChat-side session for the current acting-uid token (SSE device)."""
    try:
        chat_service.invalidate_vocechat_session(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/im/link/delete", status_code=204)
def delete_my_vocechat_account(
    payload: VocechatAccountDeleteRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete the linked VoceChat user (downstream self-delete) and remove platform mapping."""
    try:
        chat_service.delete_vocechat_account(
            db,
            current_user,
            vc,
            confirm=payload.confirm,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/conversations", response_model=ConversationListResponse)
def list_my_conversations(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    try:
        return chat_service.list_conversations(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/conversations",
    response_model=StartDirectConversationResponse,
    status_code=201,
)
def start_direct_conversation(
    payload: StartDirectConversationRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StartDirectConversationResponse:
    try:
        return chat_service.start_conversation_with_user(
            db,
            current_user,
            vc,
            target_public_id=payload.target_public_id,
            body=payload.body,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/conversations/pin", status_code=204)
def pin_conversation(
    payload: PinUnpinChatRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        chat_service.pin_chat(
            db,
            current_user,
            vc,
            conversation_id=payload.conversation_id,
            target_public_id=payload.target_public_id,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/conversations/unpin", status_code=204)
def unpin_conversation(
    payload: PinUnpinChatRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        chat_service.unpin_chat(
            db,
            current_user,
            vc,
            conversation_id=payload.conversation_id,
            target_public_id=payload.target_public_id,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/conversations/{conversation_id}/read", status_code=204)
def mark_conversation_read(
    conversation_id: _ConversationIdPath,
    payload: LastMessageReadRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        chat_service.mark_conversation_read(
            db,
            current_user,
            vc,
            conversation_id,
            payload.last_message_id,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_conversation_messages(
    conversation_id: _ConversationIdPath,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    before_message_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=300),
) -> MessageListResponse:
    try:
        return chat_service.list_messages(
            db,
            current_user,
            vc,
            conversation_id,
            before_message_id=before_message_id,
            limit=limit,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
async def send_conversation_message(
    conversation_id: _ConversationIdPath,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    """JSON ``{{"body": "..."}}`` for plain text, or ``multipart/form-data`` with part ``file``."""
    ct = (request.headers.get("content-type") or "").lower()
    try:
        if "multipart/form-data" in ct:
            form = await request.form()
            up = form.get("file")
            if not isinstance(up, UploadFile):
                raise ChatServiceError(
                    422, "multipart request must include a file field"
                )
            raw = await up.read()
            return chat_service.send_message_file(
                db,
                current_user,
                vc,
                conversation_id,
                data=raw,
                filename=up.filename,
                content_type=up.content_type,
            )
        if ct.startswith("application/json") or not ct.strip():
            body = await request.json()
            payload = ChatMessageCreateRequest.model_validate(body)
            return chat_service.send_message(
                db, current_user, vc, conversation_id, payload.body
            )
        raise ChatServiceError(
            415,
            "Content-Type must be application/json or multipart/form-data",
        )
    except ChatServiceError as exc:
        _handle(exc)


def _op_mid(mid: int) -> ChatMessageOperationResponse:
    return ChatMessageOperationResponse(message_id=str(int(mid)))


@router.put(
    "/me/conversations/{conversation_id}/messages/{message_id}/edit",
    response_model=ChatMessageOperationResponse,
)
async def edit_conversation_message(
    conversation_id: _ConversationIdPath,
    message_id: str,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    """VoceChat ``PUT /message/{{mid}}/edit``: JSON ``{{"body"}}`` or raw VoceChat content types."""
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
            mid = chat_service.edit_conversation_message(
                db,
                current_user,
                vc,
                conversation_id,
                message_id,
                json_text=payload.body,
                x_properties=x_prop_n,
            )
            return _op_mid(mid)
        raw = await request.body()
        mid = chat_service.edit_conversation_message(
            db,
            current_user,
            vc,
            conversation_id,
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
    "/me/conversations/{conversation_id}/messages/{message_id}/like",
    response_model=ChatMessageOperationResponse,
)
def like_conversation_message(
    conversation_id: _ConversationIdPath,
    message_id: str,
    payload: MessageLikeRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    """VoceChat ``PUT /message/{{mid}}/like``."""
    try:
        mid = chat_service.like_conversation_message(
            db,
            current_user,
            vc,
            conversation_id,
            message_id,
            action=payload.action,
        )
        return _op_mid(mid)
    except ChatServiceError as exc:
        _handle(exc)


@router.delete(
    "/me/conversations/{conversation_id}/messages/{message_id}",
    response_model=ChatMessageOperationResponse,
)
def delete_conversation_message(
    conversation_id: _ConversationIdPath,
    message_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    """VoceChat ``DELETE /message/{{mid}}``."""
    try:
        mid = chat_service.delete_conversation_message(
            db, current_user, vc, conversation_id, message_id
        )
        return _op_mid(mid)
    except ChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/conversations/{conversation_id}/messages/{message_id}/reply",
    response_model=ChatMessageOperationResponse,
)
async def reply_conversation_message(
    conversation_id: _ConversationIdPath,
    message_id: str,
    request: Request,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageOperationResponse:
    """VoceChat ``POST /message/{{mid}}/reply``."""
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
            mid = chat_service.reply_conversation_message(
                db,
                current_user,
                vc,
                conversation_id,
                message_id,
                json_text=payload.body,
                x_properties=x_prop_n,
            )
            return _op_mid(mid)
        raw = await request.body()
        mid = chat_service.reply_conversation_message(
            db,
            current_user,
            vc,
            conversation_id,
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
