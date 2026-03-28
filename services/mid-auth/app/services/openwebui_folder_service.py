"""Platform **Open WebUI folders** BFF: ``/me/ai/workbench/folders`` (CRUD JSON)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User


@dataclass
class OpenWebUIFolderServiceError(Exception):
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
        raise OpenWebUIFolderServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(mapping: UserAppMapping) -> str:
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise OpenWebUIFolderServiceError(404, "openwebui mapping not found") from None


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> OpenWebUIFolderServiceError:
    if exc.transport:
        return OpenWebUIFolderServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return OpenWebUIFolderServiceError(503, "openwebui response error")
    if status >= 500:
        return OpenWebUIFolderServiceError(503, "openwebui upstream error")
    if status == 404:
        return OpenWebUIFolderServiceError(404, "folder not found")
    if status == 403:
        return OpenWebUIFolderServiceError(403, "forbidden")
    if status == 401:
        return OpenWebUIFolderServiceError(404, "folder not found")
    if status == 422:
        return OpenWebUIFolderServiceError(422, "invalid request")
    if status == 400:
        return OpenWebUIFolderServiceError(400, "invalid request")
    return OpenWebUIFolderServiceError(503, "openwebui upstream error")


def list_my_openwebui_folders(
    db: Session,
    user: User,
    client: OpenWebUIClient,
) -> list[dict[str, Any]]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.list_folders(acting)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_my_openwebui_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    folder_id: str,
) -> dict[str, Any]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.get_folder(acting, folder_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def create_my_openwebui_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    body: dict[str, Any],
) -> dict[str, Any]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.create_folder(acting, body)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def update_my_openwebui_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    folder_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        return client.update_folder(acting, folder_id, body)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def delete_my_openwebui_folder(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    folder_id: str,
    *,
    delete_contents: bool = True,
) -> None:
    mapping = _require_mapping(db, user)
    acting = _acting_uid_for_client(mapping)
    try:
        client.delete_folder(acting, folder_id, delete_contents=delete_contents)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
