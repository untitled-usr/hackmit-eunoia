"""BFF: safe read-only Open WebUI ``configs`` GET for the current user (whitelist only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_safe_config import OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS
from app.models.users import User
from app.services.ai_chat_service import (
    AiChatServiceError,
    _acting_uid_for_client,
    _require_mapping,
)


def _map_config_client_error(exc: OpenWebUIClientError) -> AiChatServiceError:
    if exc.transport:
        return AiChatServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return AiChatServiceError(503, "openwebui response error")
    if status >= 500:
        return AiChatServiceError(503, "openwebui upstream error")
    if status == 404:
        return AiChatServiceError(404, "openwebui config not found")
    if status == 403:
        return AiChatServiceError(403, "forbidden")
    if status == 401:
        return AiChatServiceError(404, "openwebui user not found")
    if status == 422:
        return AiChatServiceError(422, "invalid request")
    return AiChatServiceError(503, "openwebui upstream error")


def get_my_openwebui_safe_config(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    config_key: str,
) -> Any:
    if config_key not in OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS:
        raise AiChatServiceError(404, "openwebui config not found")
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.get_configs_get_json(acting, config_key)
    except OpenWebUIClientError as exc:
        raise _map_config_client_error(exc) from exc
