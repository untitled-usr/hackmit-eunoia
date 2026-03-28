"""Current-user AI chats (OpenWebUI-backed; OW paths not exposed to clients)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.ai_chat import (
    AiChatCreateEmptyResponse,
    AiChatCreateRequest,
    AiChatCreateWithMessageResponse,
    AiChatMessageCreateRequest,
    AiChatMessagesResponse,
    AiChatsListResponse,
    AiChatSummary,
    AiChatTitlePatchRequest,
    AiMessageOut,
)
from app.services.ai_chat_service import (
    AiChatServiceError,
    append_ai_chat_message,
    create_ai_chat_empty,
    create_ai_chat_with_first_message,
    delete_ai_chat,
    get_ai_chat_messages,
    list_ai_chats,
    stream_ai_chat_message,
    update_ai_chat_title,
)

router = APIRouter()


def _handle(exc: AiChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/ai/chats", response_model=AiChatsListResponse)
def list_my_ai_chats(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatsListResponse:
    try:
        return list_ai_chats(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/ai/chats/{chat_id}/messages",
    response_model=AiChatMessagesResponse,
)
def get_my_ai_chat_messages(
    chat_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatMessagesResponse:
    try:
        return get_ai_chat_messages(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/ai/chats",
    status_code=201,
    response_model=AiChatCreateEmptyResponse | AiChatCreateWithMessageResponse,
)
def create_my_ai_chat(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    payload: AiChatCreateRequest | None = Body(default=None),
) -> AiChatCreateEmptyResponse | AiChatCreateWithMessageResponse | StreamingResponse:
    try:
        if payload is not None and payload.body is not None and payload.stream:
            _chat_id, stream_iter = stream_ai_chat_message(
                db,
                current_user,
                ow,
                chat_id=None,
                user_text=payload.body,
                model_override=payload.model,
            )
            return StreamingResponse(
                stream_iter,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        if payload is None or payload.body is None:
            return create_ai_chat_empty(db, current_user, ow)
        return create_ai_chat_with_first_message(
            db,
            current_user,
            ow,
            payload.body,
            payload.model,
        )
    except AiChatServiceError as exc:
        _handle(exc)


@router.post(
    "/me/ai/chats/{chat_id}/messages",
    response_model=AiMessageOut,
)
def append_my_ai_chat_message(
    chat_id: str,
    payload: AiChatMessageCreateRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiMessageOut | StreamingResponse:
    try:
        if payload.stream:
            _chat_id, stream_iter = stream_ai_chat_message(
                db,
                current_user,
                ow,
                chat_id=chat_id,
                user_text=payload.body,
                model_override=payload.model,
            )
            return StreamingResponse(
                stream_iter,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        return append_ai_chat_message(
            db,
            current_user,
            ow,
            chat_id,
            payload.body,
            payload.model,
        )
    except AiChatServiceError as exc:
        _handle(exc)


@router.patch(
    "/me/ai/chats/{chat_id}",
    response_model=AiChatSummary,
)
def patch_my_ai_chat(
    chat_id: str,
    payload: AiChatTitlePatchRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiChatSummary:
    try:
        return update_ai_chat_title(
            db, current_user, ow, chat_id, payload.title
        )
    except AiChatServiceError as exc:
        _handle(exc)


@router.delete("/me/ai/chats/{chat_id}", status_code=204)
def delete_my_ai_chat(
    chat_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        delete_ai_chat(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)
