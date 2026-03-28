"""Platform **Open WebUI tools** BFF: ``/me/ai/workbench/tools`` (list, detail, valves)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User


@dataclass
class OpenWebUIToolsServiceError(Exception):
    status_code: int
    detail: str


def _require_mapping(db: Session, user: User) -> UserAppMapping:
    row = (
        db.query(UserAppMapping)
        .filter(
            UserAppMapping.user_id == user.id,
            UserAppMapping.app_name == "openwebui",
        )
        .first()
    )
    if row is None:
        raise OpenWebUIToolsServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(mapping: UserAppMapping) -> str:
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise OpenWebUIToolsServiceError(404, "openwebui mapping not found") from None


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> OpenWebUIToolsServiceError:
    if exc.transport:
        return OpenWebUIToolsServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return OpenWebUIToolsServiceError(503, "openwebui response error")
    if status >= 500:
        return OpenWebUIToolsServiceError(503, "openwebui upstream error")
    if status == 404:
        return OpenWebUIToolsServiceError(404, "tool not found")
    if status == 403:
        return OpenWebUIToolsServiceError(403, "forbidden")
    if status == 401:
        return OpenWebUIToolsServiceError(404, "tool not found")
    if status == 422:
        return OpenWebUIToolsServiceError(422, "invalid request")
    if status == 400:
        return OpenWebUIToolsServiceError(400, "invalid request")
    return OpenWebUIToolsServiceError(503, "openwebui upstream error")


def list_openwebui_tools(
    db: Session,
    user: User,
    client: OpenWebUIClient,
) -> list[dict[str, Any]]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.list_tools(acting)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_openwebui_tool(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    tool_id: str,
) -> dict[str, Any]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.get_tool(acting, tool_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_openwebui_tool_valves(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    tool_id: str,
) -> dict[str, Any] | None:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.get_tool_valves(acting, tool_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def update_openwebui_tool_valves(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    tool_id: str,
    body: dict[str, Any],
) -> dict[str, Any] | None:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.update_tool_valves(acting, tool_id, body)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
