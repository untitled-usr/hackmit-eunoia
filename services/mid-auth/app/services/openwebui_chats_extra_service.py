"""Open WebUI chat extras (search / pinned / archive / tags / shared read paths).

Does **not** replace ``/me/ai/chats`` list, title patch, delete, or message APIs.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.models.users import User
from app.services.ai_chat_service import (
    AiChatServiceError,
    map_openwebui_upstream_error,
    resolve_openwebui_acting_uid,
)


def _wrap(exc: OpenWebUIClientError) -> AiChatServiceError:
    return map_openwebui_upstream_error(exc)


def ow_search_chats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    text: str,
    page: int | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.search_chats(acting, text=text, page=page)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_pinned_chats(
    db: Session, user: User, client: OpenWebUIClient
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_pinned_chats(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_archived_chats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    page: int | None,
    query: str | None,
    order_by: str | None,
    direction: str | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_archived_chats(
            acting,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_shared_chats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    page: int | None,
    query: str | None,
    order_by: str | None,
    direction: str | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_shared_chats(
            acting,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_shared_chat(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    share_id: str,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_shared_chat_by_share_id(acting, share_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_all_tags(
    db: Session, user: User, client: OpenWebUIClient
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_all_user_tags(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_by_tag(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    name: str,
    skip: int,
    limit: int,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_by_tag_name(
            acting, name=name, skip=skip, limit=limit
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_chat_pinned(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> bool | None:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_chat_pinned_flag(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_toggle_pin(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.toggle_chat_pin(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_toggle_archive(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.toggle_chat_archive(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_tags_for_chat(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_chat_tags(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_add_chat_tag(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    *,
    name: str,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.add_chat_tag(acting, chat_id, name=name)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_delete_chat_tag(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    *,
    name: str,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.delete_chat_tag(acting, chat_id, name=name)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_delete_all_chat_tags(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> bool:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.delete_all_chat_tags(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_archive_all(
    db: Session, user: User, client: OpenWebUIClient
) -> bool:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.archive_all_chats(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_unarchive_all(
    db: Session, user: User, client: OpenWebUIClient
) -> bool:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.unarchive_all_chats(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_delete_chats_bulk(db: Session, user: User, client: OpenWebUIClient) -> bool:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.delete_chats_bulk(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_all(
    db: Session, user: User, client: OpenWebUIClient
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_all(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_all_archived(
    db: Session, user: User, client: OpenWebUIClient
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_all_archived(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_all_db(
    db: Session, user: User, client: OpenWebUIClient
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_all_db(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_chats_folder(
    db: Session, user: User, client: OpenWebUIClient, folder_id: str
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_chats_folder(acting, folder_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    folder_id: str,
    *,
    page: int | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_folder(acting, folder_id, page=page)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_import_chats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    chats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.import_chats(acting, chats=chats)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_session(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    page: int | None,
    include_pinned: bool | None,
    include_folders: bool | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats(
            acting,
            page=page,
            include_pinned=include_pinned,
            include_folders=include_folders,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_chats_by_user_id(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    target_user_id: str,
    *,
    page: int | None,
    query: str | None,
    order_by: str | None,
    direction: str | None,
) -> list[dict[str, Any]]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_chats_by_user(
            acting,
            target_user_id,
            page=page,
            query=query,
            order_by=order_by,
            direction=direction,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_chat_stats_usage(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    items_per_page: int | None,
    page: int | None,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_chat_stats_usage(
            acting, items_per_page=items_per_page, page=page
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_export_chat_stats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    updated_at: int | None,
    page: int | None,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.export_chat_stats(acting, updated_at=updated_at, page=page)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_export_chat_stats_by_id(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.export_chat_stats_by_id(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_clone_chat(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    *,
    title: str | None,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.clone_chat(acting, chat_id, title=title)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_clone_shared_chat(
    db: Session, user: User, client: OpenWebUIClient, share_or_chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.clone_shared_chat(acting, share_or_chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_move_chat_to_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    *,
    folder_id: str | None,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.move_chat_to_folder(acting, chat_id, folder_id=folder_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_update_chat_message(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    message_id: str,
    *,
    content: str,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.update_chat_message(
            acting, chat_id, message_id, content=content
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_create_chat_message_event(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    message_id: str,
    *,
    event_type: str,
    data: dict[str, Any],
) -> bool:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.create_chat_message_event(
            acting,
            chat_id,
            message_id,
            event_type=event_type,
            data=data,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_delete_chat_share(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> bool | None:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.delete_chat_share(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_create_chat_share(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.create_chat_share(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_stream_export_chat_stats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    updated_at: int | None,
):
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.stream_export_chat_stats(acting, updated_at=updated_at)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
