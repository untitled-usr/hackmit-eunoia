"""Open WebUI models (read-only) for ``/me/ai/workbench/models/*`` — OW paths not exposed to clients."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User


@dataclass
class OpenWebUIModelsServiceError(Exception):
    status_code: int
    detail: str


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> OpenWebUIModelsServiceError:
    if exc.transport:
        return OpenWebUIModelsServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return OpenWebUIModelsServiceError(503, "openwebui response error")
    if status >= 500:
        return OpenWebUIModelsServiceError(503, "openwebui upstream error")
    if status == 404:
        return OpenWebUIModelsServiceError(404, "model not found")
    if status == 403:
        return OpenWebUIModelsServiceError(403, "forbidden")
    if status == 401:
        return OpenWebUIModelsServiceError(404, "model not found")
    if status == 422:
        return OpenWebUIModelsServiceError(422, "invalid request")
    return OpenWebUIModelsServiceError(503, "openwebui upstream error")


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
        raise OpenWebUIModelsServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(
    mapping: UserAppMapping, settings: Settings | None = None
) -> str:
    s = settings or get_settings()
    # Stub provisioning may store a placeholder app_uid that is not a real OW user.
    # Fall back to configured admin acting uid so model APIs remain usable in stub mode.
    if mapping.app_uid.startswith("stub-openwebui") and s.open_webui_admin_acting_uid:
        return s.open_webui_admin_acting_uid.strip()
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise OpenWebUIModelsServiceError(404, "openwebui mapping not found") from None


def _acting(db: Session, user: User) -> str:
    mapping = _require_mapping(db, user)
    return _acting_uid_for_client(mapping)


def list_workspace_models(
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
) -> dict:
    acting = _acting(db, user)
    try:
        return ow.list_models_workspace(
            acting,
            query=query,
            view_option=view_option,
            tag=tag,
            order_by=order_by,
            direction=direction,
            page=page,
        )
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_base_models(db: Session, user: User, ow: OpenWebUIClient) -> list[dict]:
    """Proxies OW ``/api/v1/models/base`` (upstream is admin-only for typical OW users)."""
    acting = _acting(db, user)
    try:
        return ow.get_models_base(acting)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_model_tags(db: Session, user: User, ow: OpenWebUIClient) -> list[str]:
    acting = _acting(db, user)
    try:
        return ow.get_model_tags(acting)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc


def get_model_detail(db: Session, user: User, ow: OpenWebUIClient, model_id: str) -> dict:
    acting = _acting(db, user)
    try:
        row = ow.get_model_by_id(acting, model_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    if row is None:
        raise OpenWebUIModelsServiceError(404, "model not found")
    return row


def get_default_model_metadata(
    db: Session, user: User, ow: OpenWebUIClient, settings: Settings | None = None
) -> dict:
    """Uses ``MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID`` then fetches that model from Open WebUI."""
    s = settings or get_settings()
    mid = (s.openwebui_default_model_id or "").strip()
    if not mid:
        raise OpenWebUIModelsServiceError(
            404, "openwebui default model not configured"
        )
    return get_model_detail(db, user, ow, mid)
