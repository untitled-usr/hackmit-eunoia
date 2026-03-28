"""Workbench metadata: version, health, safe app config, manifest (sanitized)."""

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

_SAFE_APP_CONFIG_TOP_KEYS: frozenset[str] = frozenset(
    {
        "onboarding",
        "status",
        "name",
        "version",
        "default_locale",
        "features",
        "default_models",
        "default_pinned_models",
        "default_prompt_suggestions",
        "user_count",
        "audio",
        "file",
        "ui",
    }
)


def _wrap(exc: OpenWebUIClientError) -> AiChatServiceError:
    return map_openwebui_upstream_error(exc)


def sanitize_openwebui_app_config(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw[k] for k in _SAFE_APP_CONFIG_TOP_KEYS if k in raw}


def sanitize_openwebui_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in (
        "name",
        "short_name",
        "description",
        "display",
        "background_color",
        "theme_color",
    ):
        if k in raw:
            out[k] = raw[k]
    icons = raw.get("icons")
    if isinstance(icons, list):
        safe: list[dict[str, Any]] = []
        for icon in icons:
            if not isinstance(icon, dict):
                continue
            src = icon.get("src")
            if isinstance(src, str) and src.startswith("/"):
                entry = {
                    kk: icon[kk]
                    for kk in ("src", "type", "sizes", "purpose")
                    if kk in icon
                }
                if entry:
                    safe.append(entry)
        if safe:
            out["icons"] = safe
    return out


def _redact_audio_leaf(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).upper()
            if any(x in lk for x in ("API_KEY", "SECRET", "PASSWORD", "TOKEN")):
                out[k] = bool(v) if v not in (None, "", [], {}) else False
            else:
                out[k] = _redact_audio_leaf(v)
        return out
    if isinstance(obj, list):
        return [_redact_audio_leaf(x) for x in obj]
    return obj


def redact_openwebui_audio_config(raw: dict[str, Any]) -> dict[str, Any]:
    return _redact_audio_leaf(raw)


def ow_get_version(client: OpenWebUIClient) -> dict[str, Any]:
    try:
        return client.get_version()
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_changelog(client: OpenWebUIClient) -> dict[str, Any]:
    try:
        return client.get_changelog()
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_health(client: OpenWebUIClient) -> dict[str, Any]:
    try:
        return client.get_health()
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_health_db(client: OpenWebUIClient) -> dict[str, Any]:
    try:
        return client.get_health_db()
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_manifest_safe(client: OpenWebUIClient) -> dict[str, Any]:
    try:
        raw = client.get_manifest()
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
    if not isinstance(raw, dict):
        return {}
    return sanitize_openwebui_manifest(raw)


def ow_get_version_updates(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_version_updates(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_app_config_safe(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        raw = client.get_config(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
    if not isinstance(raw, dict):
        return {}
    return sanitize_openwebui_app_config(raw)


def ow_get_usage(db: Session, user: User, client: OpenWebUIClient) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_usage(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_tasks(db: Session, user: User, client: OpenWebUIClient) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_tasks(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_task_chat(
    db: Session, user: User, client: OpenWebUIClient, chat_id: str
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.get_task_chat(acting, chat_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_stop_task(
    db: Session, user: User, client: OpenWebUIClient, task_id: str
) -> Any:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.stop_task(acting, task_id)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_get_audio_config_safe(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        raw = client.get_audio_config(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
    if not isinstance(raw, dict):
        return {}
    return redact_openwebui_audio_config(raw)


def ow_update_audio_config(
    db: Session, user: User, client: OpenWebUIClient, body: dict[str, Any]
) -> Any:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.update_audio_config(acting, body)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_audio_models(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_audio_models(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_audio_voices(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_audio_voices(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_create_audio_speech(
    db: Session, user: User, client: OpenWebUIClient, payload: dict[str, Any]
) -> Any:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.create_audio_speech(acting, payload)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_create_audio_transcription(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    file_content: bytes,
    filename: str,
    content_type: str | None,
    language: str | None,
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        raw = client.create_audio_transcription(
            acting,
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            language=language,
        )
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
    out = dict(raw)
    if "filename" in out:
        out["filename"] = str(out.get("filename") or "").split("/")[-1]
    return out


def ow_list_models_legacy(
    db: Session, user: User, client: OpenWebUIClient, *, refresh: bool = False
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_models_legacy(acting, refresh=refresh)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc


def ow_list_models_base_legacy(
    db: Session, user: User, client: OpenWebUIClient
) -> dict[str, Any]:
    acting = resolve_openwebui_acting_uid(db, user)
    try:
        return client.list_models_base_legacy(acting)
    except OpenWebUIClientError as exc:
        raise _wrap(exc) from exc
