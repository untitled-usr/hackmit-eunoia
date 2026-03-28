"""BFF: Open WebUI notes (read-only list/detail; fork ``routers/notes`` GET)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.services.ai_chat_service import AiChatServiceError, _require_mapping


def _acting_uid_for_client(mapping: UserAppMapping) -> str:
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise AiChatServiceError(404, "openwebui mapping not found") from None


def _map_notes_client_error(exc: OpenWebUIClientError) -> AiChatServiceError:
    if exc.transport:
        return AiChatServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return AiChatServiceError(503, "openwebui response error")
    if status >= 500:
        return AiChatServiceError(503, "openwebui upstream error")
    if status == 404:
        return AiChatServiceError(404, "note not found")
    if status == 403:
        return AiChatServiceError(403, "forbidden")
    if status == 401:
        return AiChatServiceError(403, "forbidden")
    if status == 422:
        return AiChatServiceError(422, "invalid request")
    if status == 400:
        return AiChatServiceError(400, "invalid request")
    return AiChatServiceError(503, "openwebui upstream error")


def list_my_openwebui_notes(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    *,
    page: int | None = None,
) -> list[dict[str, Any]]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.list_notes(acting, page=page)
    except OpenWebUIClientError as exc:
        raise _map_notes_client_error(exc) from exc


def get_my_openwebui_note(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    note_id: str,
) -> dict[str, Any]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.get_note(acting, note_id)
    except OpenWebUIClientError as exc:
        raise _map_notes_client_error(exc) from exc
