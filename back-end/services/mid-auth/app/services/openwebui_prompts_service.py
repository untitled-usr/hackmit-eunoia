"""Current-user Open WebUI prompts (BFF): acting uid from ``user_app_mappings`` (openwebui)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User


@dataclass
class OpenWebUIPromptsServiceError(Exception):
    status_code: int
    detail: str


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> OpenWebUIPromptsServiceError:
    if exc.transport:
        return OpenWebUIPromptsServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return OpenWebUIPromptsServiceError(503, "openwebui response error")
    if status >= 500:
        return OpenWebUIPromptsServiceError(503, "openwebui upstream error")
    if status == 404:
        return OpenWebUIPromptsServiceError(404, "prompt not found")
    if status == 403:
        return OpenWebUIPromptsServiceError(403, "forbidden")
    if status == 401:
        return OpenWebUIPromptsServiceError(404, "prompt not found")
    if status == 422:
        return OpenWebUIPromptsServiceError(422, "invalid request")
    if status == 400:
        return OpenWebUIPromptsServiceError(400, "invalid request")
    return OpenWebUIPromptsServiceError(503, "openwebui upstream error")


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
        raise OpenWebUIPromptsServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(mapping: UserAppMapping) -> str:
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise OpenWebUIPromptsServiceError(404, "openwebui mapping not found") from None


def _acting(db: Session, user: User, ow: OpenWebUIClient) -> tuple[str, OpenWebUIClient]:
    mapping = _require_mapping(db, user)
    return _acting_uid_for_client(mapping), ow


def list_prompts_simple(db: Session, user: User, ow: OpenWebUIClient) -> list[dict[str, Any]]:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.list_prompts(acting_uid)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def list_prompts_page(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    *,
    query: str | None = None,
    view_option: str | None = None,
    tag: str | None = None,
    order_by: str | None = None,
    direction: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.get_prompt_list(
            acting_uid,
            query=query,
            view_option=view_option,
            tag=tag,
            order_by=order_by,
            direction=direction,
            page=page,
        )
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_prompt_by_id(db: Session, user: User, ow: OpenWebUIClient, prompt_id: str) -> dict[str, Any]:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.get_prompt_by_id(acting_uid, prompt_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_prompt_by_command(
    db: Session, user: User, ow: OpenWebUIClient, command: str
) -> dict[str, Any]:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.get_prompt_by_command(acting_uid, command)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def update_prompt(
    db: Session, user: User, ow: OpenWebUIClient, prompt_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.update_prompt(acting_uid, prompt_id, body)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def delete_prompt(db: Session, user: User, ow: OpenWebUIClient, prompt_id: str) -> bool:
    acting_uid, client = _acting(db, user, ow)
    try:
        return client.delete_prompt(acting_uid, prompt_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
