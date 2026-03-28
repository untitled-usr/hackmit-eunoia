"""Platform **my posts** (module-05): current user's content via Memos, not a public feed.

Scope (semantic, routes stay ``/me/posts``):

- **Not** a public square, recommendation feed, friends timeline, or cross-user discovery.
- **List** returns only the logged-in user's own memos, by sending Memos a
  ``creator_id == <acting user>`` filter plus the usual acting identity.

**Identifiers:** Response ``id`` is the underlying Memos memo resource id (memo UID),
  not a separate platform-owned post id. No ``backend_id`` split in this version.

**Visibility:** Creates always use Memos ``PRIVATE``; clients cannot set visibility
  on create/update. Responses still expose ``visibility`` for transparency.

**Authorization:** Get / update / delete of a single post rely on Memos enforcing
  access under ``X-Acting-Uid`` (correct acting user cannot mutate others' memos).
  The platform does **not** pre-fetch the memo to compare creator before write.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.memos_client import MemosClient, MemosClientError
from app.services.memos_common import memos_client_http_tuple
from app.lib.memos_acting_uid import (
    MemosAppUidError,
    memos_acting_uid_header_value,
    memos_numeric_user_id,
)
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.posts import (
    PostListResponse,
    PostOut,
    PostReactionListResponse,
    PostReactionOut,
)

log = logging.getLogger(__name__)


@dataclass
class PostsServiceError(Exception):
    status_code: int
    detail: str


_VISIBILITY_MAP = {
    "PRIVATE": "private",
    "PROTECTED": "protected",
    "PUBLIC": "public",
    "VISIBILITY_UNSPECIFIED": "private",
}


def _normalize_body(body: str) -> str:
    return body.strip()


def _require_non_empty_body(body: str) -> str:
    s = _normalize_body(body)
    if not s:
        raise PostsServiceError(400, "body must not be empty")
    return s


def _memo_post_id_or_404(post_id: str) -> str:
    pid = post_id.strip()
    if not pid or "/" in pid:
        raise PostsServiceError(404, "post not found")
    return pid


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_ts_optional(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    return _parse_ts(str(value))


def _reaction_id_from_name(name: str | None) -> str:
    if not name or not isinstance(name, str):
        return ""
    n = name.strip()
    if "/reactions/" in n:
        return n.rsplit("/reactions/", 1)[-1].strip()
    seg = n.split("/")[-1].strip()
    return seg


def _reaction_to_out(
    raw: dict[str, Any],
    *,
    creator_map: dict[str, str],
) -> PostReactionOut:
    rid = _reaction_id_from_name(str(_pick(raw, "name") or ""))
    if not rid:
        raise PostsServiceError(502, "invalid reaction payload from backend")
    rt = str(_pick(raw, "reactionType", "reaction_type") or "")
    created = _parse_ts_optional(_pick(raw, "createTime", "create_time"))
    creator_uid = _creator_app_uid_from_raw(raw)
    cpid = creator_map.get(creator_uid) if creator_uid else None
    return PostReactionOut(
        id=rid,
        reaction_type=rt,
        created_at=created,
        creator_public_id=cpid,
    )


def _pick(d: dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def _creator_app_uid_from_raw(raw: dict[str, Any]) -> str | None:
    creator = _pick(raw, "creator")
    if not isinstance(creator, str):
        return None
    c = creator.strip()
    if not c.startswith("users/"):
        return None
    suffix = c.split("/", 1)[1].strip()
    if not suffix.isdigit():
        return None
    return f"users/{int(suffix)}"


def _memo_to_post(raw: dict[str, Any], *, creator_public_id: str | None = None) -> PostOut:
    """Map Memos memo JSON → platform DTO; ``PostOut.id`` is the Memos memo UID."""
    name = _pick(raw, "name")
    if not name or not isinstance(name, str):
        raise PostsServiceError(502, "invalid memo payload from backend")
    memo_id = name.removeprefix("memos/").strip()
    content = _pick(raw, "content")
    if content is None:
        content = ""
    vis_key = str(_pick(raw, "visibility") or "VISIBILITY_UNSPECIFIED").upper()
    visibility = _VISIBILITY_MAP.get(vis_key, "private")
    created = _parse_ts(str(_pick(raw, "createTime", "create_time") or ""))
    updated = _parse_ts(str(_pick(raw, "updateTime", "update_time") or ""))
    return PostOut(
        id=memo_id,
        body=str(content),
        creator_public_id=creator_public_id,
        visibility=visibility,
        created_at=created,
        updated_at=updated,
    )


def _map_memos_error(exc: MemosClientError) -> PostsServiceError:
    code, detail = memos_client_http_tuple(exc)
    if code == 404 and "not found" in detail:
        return PostsServiceError(404, "post not found")
    if code == 403 and detail == "forbidden":
        return PostsServiceError(404, "post not found")
    return PostsServiceError(code, detail)


class PostsService:
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
            raise PostsServiceError(404, "memos account not linked")
        return row

    def _resolve_acting(self, mapping: UserAppMapping) -> tuple[str, int]:
        try:
            header = memos_acting_uid_header_value(mapping.app_uid)
            numeric = memos_numeric_user_id(mapping.app_uid)
        except MemosAppUidError:
            log.warning("Invalid memos app_uid for mapping id=%s", mapping.id)
            raise PostsServiceError(404, "memos account not linked") from None
        return header, numeric

    def _resolve_creator_numeric_by_public_id(
        self, db: Session, creator_public_id: str
    ) -> int | None:
        target_user = (
            db.query(User).filter(User.public_id == creator_public_id.strip()).first()
        )
        if target_user is None:
            return None
        target_mapping = (
            db.query(UserAppMapping)
            .filter(
                UserAppMapping.user_id == target_user.id,
                UserAppMapping.app_name == "memos",
            )
            .first()
        )
        if target_mapping is None:
            return None
        try:
            return memos_numeric_user_id(target_mapping.app_uid)
        except MemosAppUidError:
            return None

    def _creator_public_id_map(
        self, db: Session, memos_app_uids: set[str]
    ) -> dict[str, str]:
        if not memos_app_uids:
            return {}
        rows = (
            db.query(UserAppMapping.app_uid, User.public_id)
            .join(User, User.id == UserAppMapping.user_id)
            .filter(
                UserAppMapping.app_name == "memos",
                UserAppMapping.app_uid.in_(list(memos_app_uids)),
            )
            .all()
        )
        return {str(app_uid): str(public_id) for app_uid, public_id in rows}

    def create_post(
        self, db: Session, user: User, client: MemosClient, body: str
    ) -> PostOut:
        content = _require_non_empty_body(body)
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _numeric = self._resolve_acting(mapping)
        try:
            # v1: always PRIVATE; client cannot choose visibility (see module docstring).
            raw = client.create_memo(acting_uid, content=content, visibility="PRIVATE")
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        return _memo_to_post(raw, creator_public_id=user.public_id)

    def list_posts(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        *,
        page_size: int | None,
        page_token: str | None,
        filter_expr: str | None = None,
        creator_public_id: str | None = None,
    ) -> PostListResponse:
        """List memos visible to current user with optional creator scoping."""
        mapping = self._memos_mapping_row(db, user)
        acting_uid, current_numeric = self._resolve_acting(mapping)

        creator_numeric: int | None = None
        if creator_public_id and creator_public_id.strip():
            if creator_public_id.strip() == user.public_id:
                creator_numeric = current_numeric
            else:
                creator_numeric = self._resolve_creator_numeric_by_public_id(
                    db, creator_public_id
                )
                if creator_numeric is None:
                    return PostListResponse(items=[], next_page_token=None)
        else:
            creator_numeric = current_numeric

        parts: list[str] = []
        if creator_numeric is not None:
            parts.append(f"creator_id == {int(creator_numeric)}")
            if creator_numeric != current_numeric:
                parts.append('visibility == "PUBLIC"')
        if filter_expr and filter_expr.strip():
            parts.append(f"({filter_expr.strip()})")
        filt = " && ".join(parts) if parts else None

        try:
            raw = client.list_memos(
                acting_uid,
                page_size=page_size,
                page_token=page_token or None,
                filter_expr=filt,
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        memos = raw.get("memos") or raw.get("Memos") or []
        if not isinstance(memos, list):
            memos = []
        next_tok = raw.get("nextPageToken") or raw.get("next_page_token")

        creator_uid_set: set[str] = set()
        parsed_memos: list[dict[str, Any]] = []
        for m in memos:
            if not isinstance(m, dict):
                continue
            parsed_memos.append(m)
            uid = _creator_app_uid_from_raw(m)
            if uid:
                creator_uid_set.add(uid)
        creator_map = self._creator_public_id_map(db, creator_uid_set)

        items: list[PostOut] = []
        for m in parsed_memos:
            creator_uid = _creator_app_uid_from_raw(m)
            creator_pid = creator_map.get(creator_uid) if creator_uid else None
            items.append(_memo_to_post(m, creator_public_id=creator_pid))
        return PostListResponse(
            items=items,
            next_page_token=str(next_tok) if next_tok else None,
        )

    def get_post(
        self, db: Session, user: User, client: MemosClient, post_id: str
    ) -> PostOut:
        pid = post_id.strip()
        if not pid or "/" in pid:
            raise PostsServiceError(404, "post not found")
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.get_memo(acting_uid, pid)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        creator_uid = _creator_app_uid_from_raw(raw)
        creator_map = self._creator_public_id_map(db, {creator_uid} if creator_uid else set())
        return _memo_to_post(raw, creator_public_id=creator_map.get(creator_uid) if creator_uid else None)

    def update_post(
        self, db: Session, user: User, client: MemosClient, post_id: str, body: str
    ) -> PostOut:
        content = _require_non_empty_body(body)
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.update_memo_content(acting_uid, post_id.strip(), content=content)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        creator_uid = _creator_app_uid_from_raw(raw)
        creator_map = self._creator_public_id_map(db, {creator_uid} if creator_uid else set())
        return _memo_to_post(raw, creator_public_id=creator_map.get(creator_uid) if creator_uid else None)

    def delete_post(
        self, db: Session, user: User, client: MemosClient, post_id: str
    ) -> None:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.delete_memo(acting_uid, post_id.strip())
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def memos_acting_and_user_segment(
        self, db: Session, user: User
    ) -> tuple[str, str]:
        """``X-Acting-Uid`` header value and Memos ``users/{id}`` numeric segment."""
        mapping = self._memos_mapping_row(db, user)
        acting_uid, numeric = self._resolve_acting(mapping)
        return acting_uid, str(int(numeric))

    def patch_post_memo_raw(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        *,
        update_mask: str,
        body: dict[str, Any],
    ) -> PostOut:
        pid = post_id.strip()
        if not pid or "/" in pid:
            raise PostsServiceError(404, "post not found")
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.update_memo(
                acting_uid, pid, update_mask=update_mask, body=body
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        creator_uid = _creator_app_uid_from_raw(raw)
        creator_map = self._creator_public_id_map(db, {creator_uid} if creator_uid else set())
        return _memo_to_post(raw, creator_public_id=creator_map.get(creator_uid) if creator_uid else None)

    def list_post_memo_attachments(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        *,
        page_size: int | None,
        page_token: str | None,
    ) -> dict[str, Any]:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.list_memo_attachments(
                acting_uid,
                post_id.strip(),
                page_size=page_size,
                page_token=page_token,
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def set_post_memo_attachments(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        body: dict[str, Any],
    ) -> None:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.set_memo_attachments(acting_uid, post_id.strip(), body=body)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def list_post_memo_relations(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        *,
        page_size: int | None,
        page_token: str | None,
    ) -> dict[str, Any]:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.list_memo_relations(
                acting_uid,
                post_id.strip(),
                page_size=page_size,
                page_token=page_token,
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def set_post_memo_relations(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        body: dict[str, Any],
    ) -> None:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.set_memo_relations(acting_uid, post_id.strip(), body=body)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def create_post_memo_comment(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.create_memo_comment(
                acting_uid, post_id.strip(), body=body
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def list_post_memo_comments(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        *,
        page_size: int | None,
        page_token: str | None,
        order_by: str | None,
    ) -> dict[str, Any]:
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.list_memo_comments(
                acting_uid,
                post_id.strip(),
                page_size=page_size,
                page_token=page_token,
                order_by=order_by,
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc

    def list_post_memo_reactions(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        *,
        page_size: int | None,
        page_token: str | None,
    ) -> PostReactionListResponse:
        pid = _memo_post_id_or_404(post_id)
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.list_memo_reactions(
                acting_uid,
                pid,
                page_size=page_size,
                page_token=page_token,
            )
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        reactions = raw.get("reactions") or raw.get("Reactions") or []
        if not isinstance(reactions, list):
            reactions = []
        next_tok = raw.get("nextPageToken") or raw.get("next_page_token")
        total_raw = raw.get("totalSize") or raw.get("total_size")
        creator_uid_set: set[str] = set()
        parsed: list[dict[str, Any]] = []
        for r in reactions:
            if not isinstance(r, dict):
                continue
            parsed.append(r)
            cu = _creator_app_uid_from_raw(r)
            if cu:
                creator_uid_set.add(cu)
        creator_map = self._creator_public_id_map(db, creator_uid_set)
        items = [_reaction_to_out(x, creator_map=creator_map) for x in parsed]
        total_size = int(total_raw) if total_raw is not None else None
        return PostReactionListResponse(
            items=items,
            next_page_token=str(next_tok) if next_tok else None,
            total_size=total_size,
        )

    def upsert_post_memo_reaction(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        body: dict[str, Any],
    ) -> PostReactionOut:
        pid = _memo_post_id_or_404(post_id)
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.upsert_memo_reaction(acting_uid, pid, body=body)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc
        if not isinstance(raw, dict):
            raise PostsServiceError(502, "invalid reaction payload from backend")
        cu = _creator_app_uid_from_raw(raw)
        cmap = self._creator_public_id_map(db, {cu} if cu else set())
        return _reaction_to_out(raw, creator_map=cmap)

    def delete_post_memo_reaction(
        self,
        db: Session,
        user: User,
        client: MemosClient,
        post_id: str,
        reaction_id: str,
    ) -> None:
        pid = _memo_post_id_or_404(post_id)
        rid = reaction_id.strip()
        if not rid or "/" in rid:
            raise PostsServiceError(404, "reaction not found")
        mapping = self._memos_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.delete_memo_reaction(acting_uid, pid, rid)
        except MemosClientError as exc:
            raise _map_memos_error(exc) from exc


posts_service = PostsService()
