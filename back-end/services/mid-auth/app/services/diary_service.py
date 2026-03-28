from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.memos_client import MemosClient, MemosClientError
from app.lib.memos_acting_uid import (
    MemosAppUidError,
    memos_acting_uid_header_value,
    memos_numeric_user_id,
)
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.diary import (
    DiaryEntriesReorderRequest,
    DiaryEntryCreateRequest,
    DiaryEntryListResponse,
    DiaryEntryOut,
    DiaryEntryPatchRequest,
)
from app.services.memos_common import memos_client_http_tuple

_TITLE_RE = re.compile(r"^\s*#\s+([^\n]+)\n*(.*)$", re.DOTALL)


@dataclass
class DiaryServiceError(Exception):
    status_code: int
    detail: str


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _normalize_keyword(tag: str) -> str:
    return tag.strip().lstrip("#").replace(" ", "-")


def _render_memo_content(title: str, content: str, keywords: list[str]) -> str:
    normalized_title = title.strip()
    normalized_content = content.strip()
    parts: list[str] = []
    if normalized_title:
        parts.append(f"# {normalized_title}")
    if normalized_content:
        parts.append(normalized_content)
    body = "\n\n".join(parts).strip()
    kw = [_normalize_keyword(t) for t in keywords if _normalize_keyword(t)]
    if kw:
        hashtag_line = " ".join(f"#{tag}" for tag in kw)
        body = f"{body}\n\n{hashtag_line}".strip()
    return body


def _split_title_and_content(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "", ""
    m = _TITLE_RE.match(text)
    if not m:
        return "", text
    title = m.group(1).strip()
    rest = m.group(2).strip()
    return title, rest


def _to_location(status: str, unlock_time: datetime | None, order: int | None) -> dict[str, Any]:
    unlock_ts = int(unlock_time.astimezone(UTC).timestamp()) if unlock_time else 0
    return {
        "placeholder": status if status in {"normal", "digested"} else "normal",
        "latitude": float(unlock_ts),
        "longitude": float(order or 0),
    }


def _status_from_memo(raw: dict[str, Any]) -> str:
    state = str(raw.get("state") or "").upper()
    if state == "ARCHIVED":
        return "archived"
    location = raw.get("location") or {}
    placeholder = str(location.get("placeholder") or "normal").strip().lower()
    return "digested" if placeholder == "digested" else "normal"


def _unlock_from_memo(raw: dict[str, Any]) -> tuple[datetime | None, bool]:
    location = raw.get("location") or {}
    unlock_raw = location.get("latitude")
    if unlock_raw in (None, "", 0, 0.0):
        return None, False
    ts = int(float(unlock_raw))
    unlock_dt = datetime.fromtimestamp(ts, tz=UTC)
    return unlock_dt, unlock_dt > datetime.now(UTC)


def _order_from_memo(raw: dict[str, Any]) -> int:
    location = raw.get("location") or {}
    val = location.get("longitude")
    if val in (None, ""):
        return 0
    return int(float(val))


def _memo_id(raw: dict[str, Any]) -> str:
    name = str(raw.get("name") or "")
    if not name.startswith("memos/"):
        raise DiaryServiceError(502, "invalid memo payload from backend")
    return name.removeprefix("memos/").strip()


def _map_memos_error(exc: MemosClientError) -> DiaryServiceError:
    code, detail = memos_client_http_tuple(exc)
    if code == 404:
        return DiaryServiceError(404, "diary entry not found")
    return DiaryServiceError(code, detail)


class DiaryService:
    def _memos_mapping_row(self, db: Session, user: User) -> UserAppMapping:
        row = (
            db.query(UserAppMapping)
            .filter(
                UserAppMapping.user_id == user.id,
                UserAppMapping.app_name == "memos",
            )
            .first()
        )
        if row is None:
            raise DiaryServiceError(404, "memos account not linked")
        return row

    def _resolve_acting(self, mapping: UserAppMapping) -> tuple[str, int]:
        try:
            header = memos_acting_uid_header_value(mapping.app_uid)
            numeric = memos_numeric_user_id(mapping.app_uid)
        except MemosAppUidError:
            raise DiaryServiceError(404, "memos account not linked") from None
        return header, numeric

    def _memo_to_entry(self, raw: dict[str, Any]) -> DiaryEntryOut:
        entry_id = _memo_id(raw)
        title, content = _split_title_and_content(str(raw.get("content") or ""))
        status = _status_from_memo(raw)
        unlock_time, locked = _unlock_from_memo(raw)
        keywords = [str(t) for t in (raw.get("tags") or []) if isinstance(t, str)]
        return DiaryEntryOut(
            id=entry_id,
            title=title,
            content=content,
            keywords=keywords,
            status=status,  # type: ignore[arg-type]
            locked=locked,
            unlock_time=unlock_time,
            order=_order_from_memo(raw),
            created_at=_parse_ts(str(raw.get("createTime") or "")),
            updated_at=_parse_ts(str(raw.get("updateTime") or "")),
        )

    def _get_memo_or_404(
        self, db: Session, user: User, client: MemosClient, entry_id: str
    ) -> tuple[str, int, dict[str, Any]]:
        if not entry_id.strip() or "/" in entry_id:
            raise DiaryServiceError(404, "diary entry not found")
        mapping = self._memos_mapping_row(db, user)
        acting_uid, numeric_uid = self._resolve_acting(mapping)
        try:
            raw = client.get_memo(acting_uid, entry_id.strip())
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        return acting_uid, numeric_uid, raw

    def list_entries(self, db: Session, user: User, client: MemosClient) -> DiaryEntryListResponse:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, numeric_uid = self._resolve_acting(mapping)
        filt = f"creator_id == {int(numeric_uid)}"
        try:
            normal = client.list_memos(
                acting_uid,
                page_size=500,
                filter_expr=filt,
                state="NORMAL",
                order_by="diary_order asc, update_time desc",
            )
            archived = client.list_memos(
                acting_uid,
                page_size=500,
                filter_expr=filt,
                state="ARCHIVED",
                order_by="diary_order asc, update_time desc",
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

        memos = []
        for block in (normal, archived):
            rows = block.get("memos") or []
            if isinstance(rows, list):
                memos.extend(x for x in rows if isinstance(x, dict))

        items = [self._memo_to_entry(m) for m in memos]
        items.sort(key=lambda x: (x.order, x.updated_at), reverse=False)
        return DiaryEntryListResponse(items=items)

    def create_entry(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        payload: DiaryEntryCreateRequest,
    ) -> DiaryEntryOut:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _numeric_uid = self._resolve_acting(mapping)
        content = _render_memo_content(payload.title, payload.content, payload.keywords)
        if not content:
            raise DiaryServiceError(400, "title/content must not both be empty")
        try:
            raw = client.create_memo(
                acting_uid,
                content=content,
                visibility="PRIVATE",
                location=_to_location(payload.status, payload.unlock_time, payload.order),
            )
            if payload.status == "archived":
                memo_id = _memo_id(raw)
                raw = client.update_memo(
                    acting_uid,
                    memo_id,
                    update_mask="state",
                    body={"name": f"memos/{memo_id}", "state": "ARCHIVED"},
                )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        return self._memo_to_entry(raw)

    def patch_entry(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        entry_id: str,
        payload: DiaryEntryPatchRequest,
    ) -> DiaryEntryOut:
        acting_uid, _numeric_uid, current = self._get_memo_or_404(db, user, client, entry_id)
        current_entry = self._memo_to_entry(current)

        title = payload.title if payload.title is not None else current_entry.title
        content = payload.content if payload.content is not None else current_entry.content
        keywords = payload.keywords if payload.keywords is not None else current_entry.keywords
        status = payload.status if payload.status is not None else current_entry.status
        unlock_time = payload.unlock_time if payload.unlock_time is not None else current_entry.unlock_time
        order = payload.order if payload.order is not None else current_entry.order

        body = {
            "name": f"memos/{entry_id}",
            "content": _render_memo_content(title, content, keywords),
            "location": _to_location(status, unlock_time, order),
        }
        if not body["content"]:
            raise DiaryServiceError(400, "title/content must not both be empty")
        try:
            raw = client.update_memo(
                acting_uid,
                entry_id,
                update_mask="content,location",
                body=body,
            )
            target_state = "ARCHIVED" if status == "archived" else "NORMAL"
            if str(raw.get("state") or "").upper() != target_state:
                raw = client.update_memo(
                    acting_uid,
                    entry_id,
                    update_mask="state",
                    body={"name": f"memos/{entry_id}", "state": target_state},
                )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        return self._memo_to_entry(raw)

    def reorder_entries(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        payload: DiaryEntriesReorderRequest,
    ) -> DiaryEntryListResponse:
        if not payload.entries:
            return DiaryEntryListResponse(items=[])

        updated: list[DiaryEntryOut] = []
        for item in payload.entries:
            patch_payload = DiaryEntryPatchRequest(order=item.order)
            updated.append(self.patch_entry(db, user, client, item.id, patch_payload))
        updated.sort(key=lambda x: x.order)
        return DiaryEntryListResponse(items=updated)


diary_service = DiaryService()

