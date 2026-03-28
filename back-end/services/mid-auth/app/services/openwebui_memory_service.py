"""Platform Open WebUI **memories** BFF: ``/me/ai/workbench/memories``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.openwebui_memories import (
    MemoryItemOut,
    MemoryQueryHitOut,
    MemoryQueryResponse,
    MemoriesListResponse,
    MemoryResetResponse,
)


@dataclass
class OpenWebUIMemoryServiceError(Exception):
    status_code: int
    detail: str


def _utc_from_unix_seconds(ts: Any) -> datetime:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> OpenWebUIMemoryServiceError:
    if exc.transport:
        return OpenWebUIMemoryServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return OpenWebUIMemoryServiceError(503, "openwebui response error")
    if status >= 500:
        return OpenWebUIMemoryServiceError(503, "openwebui upstream error")
    if status == 404:
        return OpenWebUIMemoryServiceError(404, "openwebui resource not found")
    if status == 403:
        return OpenWebUIMemoryServiceError(403, "forbidden")
    if status == 401:
        return OpenWebUIMemoryServiceError(404, "openwebui resource not found")
    if status == 422:
        return OpenWebUIMemoryServiceError(422, "invalid request")
    return OpenWebUIMemoryServiceError(503, "openwebui upstream error")


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
        raise OpenWebUIMemoryServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(mapping: UserAppMapping) -> str:
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise OpenWebUIMemoryServiceError(404, "openwebui mapping not found") from None


def _item_from_ow(row: dict[str, Any]) -> MemoryItemOut:
    return MemoryItemOut(
        id=str(row.get("id", "")),
        body=str(row.get("content") or ""),
        updated_at=_utc_from_unix_seconds(row.get("updated_at")),
        created_at=_utc_from_unix_seconds(row.get("created_at")),
    )


def _normalize_query_hits(raw: Any) -> list[MemoryQueryHitOut]:
    if not isinstance(raw, dict):
        return []
    ids = raw.get("ids")
    docs = raw.get("documents")
    dists = raw.get("distances")
    if not ids or not isinstance(ids, list) or not ids:
        return []
    first_ids = ids[0]
    first_docs = docs[0] if isinstance(docs, list) and docs else []
    first_dists = dists[0] if isinstance(dists, list) and dists else []
    if not isinstance(first_ids, list):
        return []
    out: list[MemoryQueryHitOut] = []
    for i, mid in enumerate(first_ids):
        body = ""
        if isinstance(first_docs, list) and i < len(first_docs) and first_docs[i] is not None:
            body = str(first_docs[i])
        score: float | None = None
        if isinstance(first_dists, list) and i < len(first_dists):
            try:
                score = float(first_dists[i])
            except (TypeError, ValueError):
                score = None
        out.append(MemoryQueryHitOut(id=str(mid), body=body, score=score))
    return out


def list_memories(
    db: Session, user: User, ow: OpenWebUIClient
) -> MemoriesListResponse:
    mapping = _require_mapping(db, user)
    uid = _acting_uid_for_client(mapping)
    try:
        rows = ow.memories_list(uid)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    return MemoriesListResponse(items=[_item_from_ow(r) for r in rows])


def add_memory(db: Session, user: User, ow: OpenWebUIClient, *, body: str) -> MemoryItemOut:
    text = body.strip()
    if not text:
        raise OpenWebUIMemoryServiceError(400, "body is required")
    mapping = _require_mapping(db, user)
    uid = _acting_uid_for_client(mapping)
    try:
        row = ow.memories_add(uid, content=text)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    if row is None:
        raise OpenWebUIMemoryServiceError(503, "openwebui could not persist memory")
    return _item_from_ow(row)


def query_memories(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    *,
    body: str,
    limit: int | None,
) -> MemoryQueryResponse:
    text = body.strip()
    if not text:
        raise OpenWebUIMemoryServiceError(400, "body is required")
    mapping = _require_mapping(db, user)
    uid = _acting_uid_for_client(mapping)
    try:
        raw = ow.memories_query(uid, content=text, k=limit)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    return MemoryQueryResponse(items=_normalize_query_hits(raw))


def reset_memories(db: Session, user: User, ow: OpenWebUIClient) -> MemoryResetResponse:
    mapping = _require_mapping(db, user)
    uid = _acting_uid_for_client(mapping)
    try:
        ok = ow.memories_reset(uid)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    return MemoryResetResponse(ok=ok)


def update_memory(
    db: Session,
    user: User,
    ow: OpenWebUIClient,
    memory_id: str,
    *,
    body: str,
) -> MemoryItemOut:
    text = body.strip()
    if not text:
        raise OpenWebUIMemoryServiceError(400, "body is required")
    mid = (memory_id or "").strip()
    if not mid:
        raise OpenWebUIMemoryServiceError(400, "memory id is required")
    mapping = _require_mapping(db, user)
    uid = _acting_uid_for_client(mapping)
    try:
        row = ow.memories_update(uid, mid, content=text)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    if row is None:
        raise OpenWebUIMemoryServiceError(404, "openwebui resource not found")
    return _item_from_ow(row)
