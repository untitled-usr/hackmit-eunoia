"""Open WebUI chat BFF extras; primary paths ``/me/ai/workbench/chats*`` (not ``/me/ai/chats*``)."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.integrations.openwebui_client import OpenWebUIClient
from app.models.users import User
from app.schemas.openwebui_chats_extra import (
    OpenWebuiChatsTagFilterBody,
    OpenWebuiChatsTagNameBody,
)
from app.schemas.openwebui_gap_requests import (
    OpenWebuiChatMessageContentBody,
    OpenWebuiChatMessageEventBody,
    OpenWebuiChatMoveFolderBody,
    OpenWebuiChatsImportBody,
    OpenWebuiCloneChatBody,
)
from app.services.ai_chat_service import AiChatServiceError
from app.services import openwebui_chats_extra_service as ow_x

router = APIRouter()


def _handle(exc: AiChatServiceError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def openwebui_search_chats(
    text: str = Query(
        ...,
        min_length=1,
        description="Open WebUI search text (incl. tag:/pinned:/archived: tokens).",
    ),
    page: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_search_chats(db, current_user, ow, text=text, page=page)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_pinned_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_pinned_chats(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_archived_chats(
    page: int | None = Query(default=None, ge=1),
    query: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_archived_chats(
            db,
            current_user,
            ow,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_shared_chats(
    page: int | None = Query(default=None, ge=1),
    query: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_shared_chats(
            db,
            current_user,
            ow,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_get_shared_chat(
    share_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_get_shared_chat(db, current_user, ow, share_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_tag_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_all_tags(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_chats_by_tag(
    payload: OpenWebuiChatsTagFilterBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_by_tag(
            db,
            current_user,
            ow,
            name=payload.name,
            skip=payload.skip,
            limit=payload.limit,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_archive_all_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool]:
    try:
        ok = ow_x.ow_archive_all(db, current_user, ow)
        return {"ok": ok}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_unarchive_all_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool]:
    try:
        ok = ow_x.ow_unarchive_all(db, current_user, ow)
        return {"ok": ok}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_get_chat_pinned(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool | None]:
    try:
        flag = ow_x.ow_get_chat_pinned(db, current_user, ow, chat_id)
        return {"pinned": flag}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_toggle_pin(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_toggle_pin(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_toggle_archive(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_toggle_archive(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_get_tags(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_get_tags_for_chat(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_add_tag(
    chat_id: str,
    payload: OpenWebuiChatsTagNameBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_add_chat_tag(db, current_user, ow, chat_id, name=payload.name)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_delete_tag(
    chat_id: str,
    payload: OpenWebuiChatsTagNameBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_delete_chat_tag(
            db, current_user, ow, chat_id, name=payload.name
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_delete_all_tags(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool]:
    try:
        ok = ow_x.ow_delete_all_chat_tags(db, current_user, ow, chat_id)
        return {"ok": ok}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_delete_chats_bulk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool]:
    try:
        ok = ow_x.ow_delete_chats_bulk(db, current_user, ow)
        return {"ok": ok}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_chats_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_all(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_chats_all_archived(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_all_archived(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_chats_all_db(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_all_db(db, current_user, ow)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_chats_by_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_get_chats_folder(db, current_user, ow, folder_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_chats_folder_list(
    folder_id: str,
    page: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_folder(
            db, current_user, ow, folder_id, page=page
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_import_chats(
    payload: OpenWebuiChatsImportBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_import_chats(
            db, current_user, ow, chats=payload.chats
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_chats_compat(
    page: int | None = Query(default=None, ge=1),
    include_pinned: bool | None = Query(default=None),
    include_folders: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_session(
            db,
            current_user,
            ow,
            page=page,
            include_pinned=include_pinned,
            include_folders=include_folders,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_list_chats_by_user(
    user_id: str,
    page: int | None = Query(default=None, ge=1),
    query: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> list[dict[str, Any]]:
    try:
        return ow_x.ow_list_chats_by_user_id(
            db,
            current_user,
            ow,
            user_id,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_chat_stats_usage(
    items_per_page: int | None = Query(default=None, ge=1, le=500),
    page: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_get_chat_stats_usage(
            db,
            current_user,
            ow,
            items_per_page=items_per_page,
            page=page,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_export_chat_stats(
    updated_at: int | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_export_chat_stats(
            db, current_user, ow, updated_at=updated_at, page=page
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_export_chat_stats_stream(
    updated_at: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
):
    try:
        stream = ow_x.ow_stream_export_chat_stats(
            db, current_user, ow, updated_at=updated_at
        )
    except AiChatServiceError as exc:
        _handle(exc)
    media = stream.response.headers.get("content-type", "application/x-ndjson")

    def gen():
        yield from stream.iter_bytes()

    return StreamingResponse(
        gen(),
        media_type=media,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "attachment; filename=chat-stats.jsonl",
        },
    )


def openwebui_export_chat_stats_one(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_export_chat_stats_by_id(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_clone_chat(
    chat_id: str,
    payload: OpenWebuiCloneChatBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_clone_chat(
            db, current_user, ow, chat_id, title=payload.title
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_clone_shared_chat(
    share_or_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_clone_shared_chat(db, current_user, ow, share_or_id)
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_move_chat_folder(
    chat_id: str,
    payload: OpenWebuiChatMoveFolderBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_move_chat_to_folder(
            db, current_user, ow, chat_id, folder_id=payload.folder_id
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_update_chat_message(
    chat_id: str,
    message_id: str,
    payload: OpenWebuiChatMessageContentBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_update_chat_message(
            db,
            current_user,
            ow,
            chat_id,
            message_id,
            content=payload.content,
        )
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_chat_message_event(
    chat_id: str,
    message_id: str,
    payload: OpenWebuiChatMessageEventBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool]:
    try:
        ok = ow_x.ow_create_chat_message_event(
            db,
            current_user,
            ow,
            chat_id,
            message_id,
            event_type=payload.type,
            data=payload.data,
        )
        return {"ok": ok}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_delete_chat_share(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, bool | None]:
    try:
        r = ow_x.ow_delete_chat_share(db, current_user, ow, chat_id)
        return {"ok": r}
    except AiChatServiceError as exc:
        _handle(exc)


def openwebui_create_chat_share(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ow: OpenWebUIClient = Depends(get_openwebui_client),
) -> dict[str, Any]:
    try:
        return ow_x.ow_create_chat_share(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        _handle(exc)


register_workbench_route(
    router,
    "/chats/search",
    openwebui_search_chats,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_search",
)
register_workbench_route(
    router,
    "/chats/pinned",
    openwebui_list_pinned_chats,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_pinned",
)
register_workbench_route(
    router,
    "/chats/archived",
    openwebui_list_archived_chats,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_archived",
)
register_workbench_route(
    router,
    "/chats/shared",
    openwebui_list_shared_chats,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_shared",
)
register_workbench_route(
    router,
    "/chats/shares/{share_id}",
    openwebui_get_shared_chat,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chats_share_get",
)
register_workbench_route(
    router,
    "/chats/tag-catalog",
    openwebui_tag_catalog,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_tag_catalog",
)
register_workbench_route(
    router,
    "/chats/tag-filter",
    openwebui_chats_by_tag,
    methods=["POST"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_tag_filter",
)
register_workbench_route(
    router,
    "/chats/archive-all",
    openwebui_archive_all_chats,
    methods=["POST"],
    response_model=dict[str, bool],
    operation_id="me_ai_workbench_ow_chats_archive_all",
)
register_workbench_route(
    router,
    "/chats/unarchive-all",
    openwebui_unarchive_all_chats,
    methods=["POST"],
    response_model=dict[str, bool],
    operation_id="me_ai_workbench_ow_chats_unarchive_all",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/pinned",
    openwebui_get_chat_pinned,
    methods=["GET"],
    response_model=dict[str, bool | None],
    operation_id="me_ai_workbench_ow_chat_pinned_get",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/pin",
    openwebui_toggle_pin,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_pin",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/archive",
    openwebui_toggle_archive,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_archive",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/tags",
    openwebui_get_tags,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chat_tags_get",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/tags",
    openwebui_add_tag,
    methods=["POST"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chat_tags_add",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/tags",
    openwebui_delete_tag,
    methods=["DELETE"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chat_tags_delete",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/tags/all",
    openwebui_delete_all_tags,
    methods=["DELETE"],
    response_model=dict[str, bool],
    operation_id="me_ai_workbench_ow_chat_tags_delete_all",
)
register_workbench_route(
    router,
    "/chats/bulk",
    openwebui_delete_chats_bulk,
    methods=["DELETE"],
    response_model=dict[str, bool],
    operation_id="me_ai_workbench_ow_chats_delete_bulk",
)
register_workbench_route(
    router,
    "/chats/all",
    openwebui_list_chats_all,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_all",
)
register_workbench_route(
    router,
    "/chats/all/archived",
    openwebui_list_chats_all_archived,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_all_archived",
)
register_workbench_route(
    router,
    "/chats/all/db",
    openwebui_list_chats_all_db,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_all_db",
)
register_workbench_route(
    router,
    "/chats/folder/{folder_id}",
    openwebui_chats_by_folder,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_folder",
)
register_workbench_route(
    router,
    "/chats/folder/{folder_id}/list",
    openwebui_chats_folder_list,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_folder_list",
)
register_workbench_route(
    router,
    "/chats/import",
    openwebui_import_chats,
    methods=["POST"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_import",
)
register_workbench_route(
    router,
    "/chats/list",
    openwebui_list_chats_compat,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_list_compat",
)
register_workbench_route(
    router,
    "/chats/list/user/{user_id}",
    openwebui_list_chats_by_user,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_ow_chats_list_by_user",
)
register_workbench_route(
    router,
    "/chats/stats/usage",
    openwebui_chat_stats_usage,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chats_stats_usage",
)
register_workbench_route(
    router,
    "/chats/stats/export",
    openwebui_export_chat_stats,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chats_stats_export",
)
register_workbench_route(
    router,
    "/chats/stats/export/stream",
    openwebui_export_chat_stats_stream,
    methods=["GET"],
    response_model=None,
    operation_id="me_ai_workbench_ow_chats_stats_export_stream",
)
register_workbench_route(
    router,
    "/chats/stats/export/{chat_id}",
    openwebui_export_chat_stats_one,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chats_stats_export_one",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/clone",
    openwebui_clone_chat,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_clone",
)
register_workbench_route(
    router,
    "/chats/{share_or_id}/clone/shared",
    openwebui_clone_shared_chat,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_clone_shared",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/folder",
    openwebui_move_chat_folder,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_move_folder",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/messages/{message_id}",
    openwebui_update_chat_message,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_message_update",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/messages/{message_id}/event",
    openwebui_chat_message_event,
    methods=["POST"],
    response_model=dict[str, bool],
    operation_id="me_ai_workbench_ow_chat_message_event",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/share",
    openwebui_delete_chat_share,
    methods=["DELETE"],
    response_model=dict[str, bool | None],
    operation_id="me_ai_workbench_ow_chat_share_delete",
)
register_workbench_route(
    router,
    "/chats/{chat_id}/share",
    openwebui_create_chat_share,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_ow_chat_share_create",
)
