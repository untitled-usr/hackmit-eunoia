"""BFF: current user's Open WebUI skills & functions (read-only GET, JSON passthrough)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.models.users import User
from app.services.ai_chat_service import (
    AiChatServiceError,
    _acting_uid_for_client,
    _require_mapping,
)
from app.services.openwebui_session_service import _map_session_client_error


def list_my_skills(db: Session, user: User, ow: OpenWebUIClient) -> Any:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.list_skills(acting)
    except OpenWebUIClientError as exc:
        raise _map_session_client_error(exc) from exc


def get_my_skill(db: Session, user: User, ow: OpenWebUIClient, skill_id: str) -> Any:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.get_skill(acting, skill_id)
    except OpenWebUIClientError as exc:
        raise _map_session_client_error(exc) from exc


def list_my_functions(db: Session, user: User, ow: OpenWebUIClient) -> Any:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.list_functions(acting)
    except OpenWebUIClientError as exc:
        raise _map_session_client_error(exc) from exc


def get_my_function(
    db: Session, user: User, ow: OpenWebUIClient, function_id: str
) -> Any:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return ow.get_function(acting, function_id)
    except OpenWebUIClientError as exc:
        raise _map_session_client_error(exc) from exc
