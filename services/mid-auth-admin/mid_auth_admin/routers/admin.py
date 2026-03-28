from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mid_auth_admin.mid_auth_loader import (
    ProvisionLog,
    User,
    UserAppMapping,
    UserSession,
    VirtmateSessionMessage,
    VirtmateSessionSettings,
    VirtmateSessionState,
    VirtmateUserGlobal,
    get_mid_auth_db,
)
from mid_auth_admin.schemas.admin_payload import AdminPayload

router = APIRouter()

MAX_BLOB_BYTES = int(os.getenv("MID_AUTH_ADMIN_MAX_BLOB_BYTES", str(8 * 1024 * 1024)))
MAX_PAGE_SIZE = int(os.getenv("MID_AUTH_ADMIN_MAX_PAGE_SIZE", "200"))


@dataclass(frozen=True)
class ResourceConfig:
    name: str
    model: type
    pk_field: str = "id"
    pk_type: str = "int"
    json_text_fields: tuple[str, ...] = ()
    binary_base64_fields: tuple[str, ...] = ()
    readonly_fields: tuple[str, ...] = ("created_at", "updated_at")


RESOURCE_CONFIGS: dict[str, ResourceConfig] = {
    "users": ResourceConfig(
        name="users",
        model=User,
        pk_type="str",
        json_text_fields=(),
        binary_base64_fields=("avatar_data",),
        readonly_fields=("created_at", "updated_at"),
    ),
    "user_app_mappings": ResourceConfig(
        name="user_app_mappings",
        model=UserAppMapping,
    ),
    "sessions": ResourceConfig(
        name="sessions",
        model=UserSession,
        readonly_fields=("created_at", "last_seen_at"),
    ),
    "provision_logs": ResourceConfig(
        name="provision_logs",
        model=ProvisionLog,
        readonly_fields=("created_at",),
    ),
    "virtmate_user_globals": ResourceConfig(
        name="virtmate_user_globals",
        model=VirtmateUserGlobal,
        json_text_fields=("config_json",),
    ),
    "virtmate_session_settings": ResourceConfig(
        name="virtmate_session_settings",
        model=VirtmateSessionSettings,
        json_text_fields=("settings_json",),
    ),
    "virtmate_session_states": ResourceConfig(
        name="virtmate_session_states",
        model=VirtmateSessionState,
        json_text_fields=("state_json",),
    ),
    "virtmate_session_messages": ResourceConfig(
        name="virtmate_session_messages",
        model=VirtmateSessionMessage,
        readonly_fields=("created_at",),
    ),
}


def _resource_or_404(resource: str) -> ResourceConfig:
    config = RESOURCE_CONFIGS.get(resource)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Unknown resource: {resource}")
    return config


def _parse_bool(text: str) -> bool:
    value = text.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {text}")


def _parse_pk(pk_raw: str, config: ResourceConfig) -> int | str:
    if config.pk_type == "str":
        return pk_raw
    try:
        return int(pk_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Primary key type mismatch") from exc


def _deserialize_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _serialize_row(row: Any, config: ResourceConfig) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        key = column.name
        value = getattr(row, key)
        if key in config.binary_base64_fields and value is not None:
            result[key] = base64.b64encode(value).decode("utf-8")
            continue
        if key in config.json_text_fields:
            result[key] = _deserialize_json_field(value)
            continue
        if isinstance(value, datetime):
            result[key] = value.isoformat()
            continue
        result[key] = value
    return result


def _normalize_datetime_value(value: Any) -> Any:
    if isinstance(value, datetime) or value is None:
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid datetime: {value}") from exc
    raise HTTPException(status_code=422, detail="Datetime value must be ISO8601 string or null")


def _coerce_payload(
    payload: dict[str, Any],
    config: ResourceConfig,
    *,
    for_update: bool,
) -> dict[str, Any]:
    columns = {c.name: c for c in config.model.__table__.columns}
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in columns:
            raise HTTPException(status_code=422, detail=f"Unknown field: {key}")
        if for_update and key == config.pk_field:
            raise HTTPException(status_code=422, detail="Primary key cannot be updated")
        if key in config.readonly_fields:
            raise HTTPException(status_code=422, detail=f"Field is readonly: {key}")
        if key in config.json_text_fields:
            if isinstance(value, (dict, list)):
                normalized[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, str):
                _deserialize_json_field(value)
                normalized[key] = value
            else:
                raise HTTPException(
                    status_code=422, detail=f"Field {key} must be JSON object/array/string"
                )
            continue
        if key in config.binary_base64_fields:
            if value is None:
                normalized[key] = None
                continue
            if not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"Field {key} must be base64 string")
            try:
                decoded = base64.b64decode(value, validate=True)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=422, detail=f"Field {key} is not valid base64") from exc
            if len(decoded) > MAX_BLOB_BYTES:
                raise HTTPException(status_code=422, detail=f"Field {key} exceeds max size")
            normalized[key] = decoded
            continue
        python_type = None
        try:
            python_type = columns[key].type.python_type
        except NotImplementedError:
            python_type = None
        if python_type is datetime:
            normalized[key] = _normalize_datetime_value(value)
        else:
            normalized[key] = value
    return normalized


def _coerce_filter_value(column: Any, value: str) -> Any:
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is bool:
        return _parse_bool(value)
    if python_type is int:
        return int(value)
    if python_type is datetime:
        return datetime.fromisoformat(value)
    return value


def _apply_integrity_error(exc: IntegrityError) -> None:
    message = str(exc.orig) if exc.orig is not None else str(exc)
    raise HTTPException(status_code=409, detail=message)


@router.get("/{resource}")
def list_resource(
    resource: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_mid_auth_db),
) -> dict[str, Any]:
    config = _resource_or_404(resource)
    columns = {c.name: c for c in config.model.__table__.columns}
    statement = select(config.model)
    for key, value in request.query_params.items():
        if key in {"limit", "offset"}:
            continue
        column = columns.get(key)
        if column is None or key in config.binary_base64_fields:
            continue
        try:
            typed_value = _coerce_filter_value(column, value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid filter {key}={value}") from exc
        statement = statement.where(column == typed_value)
    rows = db.execute(statement.offset(offset).limit(limit)).scalars().all()
    return {
        "resource": config.name,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_row(row, config) for row in rows],
    }


@router.get("/{resource}/{pk}")
def get_resource_item(
    resource: str,
    pk: str,
    db: Session = Depends(get_mid_auth_db),
) -> dict[str, Any]:
    config = _resource_or_404(resource)
    pk_value = _parse_pk(pk, config)
    statement = select(config.model).where(getattr(config.model, config.pk_field) == pk_value)
    row = db.execute(statement).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize_row(row, config)


@router.post("/{resource}", status_code=status.HTTP_201_CREATED)
def create_resource_item(
    resource: str,
    payload: AdminPayload = Body(...),
    db: Session = Depends(get_mid_auth_db),
) -> dict[str, Any]:
    config = _resource_or_404(resource)
    body = _coerce_payload(payload.root, config, for_update=False)
    row = config.model(**body)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _apply_integrity_error(exc)
    db.refresh(row)
    return _serialize_row(row, config)


@router.patch("/{resource}/{pk}")
def patch_resource_item(
    resource: str,
    pk: str,
    payload: AdminPayload = Body(...),
    db: Session = Depends(get_mid_auth_db),
) -> dict[str, Any]:
    config = _resource_or_404(resource)
    pk_value = _parse_pk(pk, config)
    statement = select(config.model).where(getattr(config.model, config.pk_field) == pk_value)
    row = db.execute(statement).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    body = _coerce_payload(payload.root, config, for_update=True)
    for key, value in body.items():
        setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _apply_integrity_error(exc)
    db.refresh(row)
    return _serialize_row(row, config)


@router.delete("/{resource}/{pk}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource_item(
    resource: str,
    pk: str,
    db: Session = Depends(get_mid_auth_db),
) -> Response:
    config = _resource_or_404(resource)
    pk_value = _parse_pk(pk, config)
    statement = select(config.model).where(getattr(config.model, config.pk_field) == pk_value)
    row = db.execute(statement).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

