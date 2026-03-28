"""Platform 1:1 chat (module-06) via VoceChat; HTTP request/response for most routes.

**Real-time exception:** ``GET /me/im/events`` proxies VoceChat SSE (long-lived HTTP
stream). See ``app.services.vocechat_events_proxy``.

**Conversations list:** Built from VoceChat contacts for peer ids (see ``ConversationOut``).
``peer_display_name`` is filled from the platform ``users`` table (VoceChat uid → mapping),
not from VoceChat contact ``target_info``. This is **not** a full historical session index.

**conversation_id:** The peer's VoceChat user id (string). Not a mid-auth id.

**Authorization:** History read and send rely on VoceChat checks under ``X-Acting-Uid``.
No extra platform ACL and no mandatory “must be in contacts” gate before send.

**module-09:** ``POST /me/conversations`` resolves target by ``public_id``, then ``send_dm_text``.

**DM files:** ``POST /me/conversations/{id}/messages`` with ``multipart/form-data`` part
``file`` uploads bytes via VoceChat ``/resource/file/prepare`` + ``/resource/file/upload``,
then sends ``vocechat/file`` metadata to ``/user/{peer}/send``. VoceChat paths are not
exposed to clients.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from app.core.proxy_safety import (
    filter_allowlisted_proxy_response_headers,
    is_safe_content_disposition_value,
)
from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError
from app.lib.vocechat_acting_uid import (
    VoceChatAppUidError,
    vocechat_acting_uid_header_value,
    vocechat_numeric_user_id,
)
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.chat import (
    ConversationListResponse,
    ConversationOut,
    MessageAttachmentOut,
    MessageListResponse,
    MessageOut,
    StartDirectConversationResponse,
)
from app.schemas.chat_resources import CreateMessageArchiveBody
from app.schemas.favorites import (
    CreateFavoriteBody,
    FavoriteArchiveOut,
    FavoriteListResponse,
)

log = logging.getLogger(__name__)

# DM multipart uploads: platform buffers then pushes to VoceChat ``/resource/file/*``.
_MAX_DM_FILE_BYTES = 32 * 1024 * 1024

# VoceChat ``PUT /message/{{mid}}/edit`` and ``POST .../reply`` (same family as group send).
_VOCE_MESSAGE_EDIT_MIMES = frozenset(
    {"text/plain", "text/markdown", "vocechat/file", "vocechat/archive"}
)


def _message_main_mime(content_type: str) -> str:
    return (content_type or "").split(";", maxsplit=1)[0].strip().lower()


def _voce_outbound_content_type(incoming_header: str, main: str) -> str:
    h = incoming_header.strip()
    if main == "text/plain" and "charset" not in h.lower():
        return "text/plain; charset=utf-8"
    return h or main


@dataclass
class ChatServiceError(Exception):
    status_code: int
    detail: str


def _normalize_body(body: str) -> str:
    return body.strip()


def _require_non_empty_body(body: str) -> str:
    s = _normalize_body(body)
    if not s:
        raise ChatServiceError(400, "body must not be empty")
    return s


def _parse_voce_message_id(message_id: str) -> int:
    raw = message_id.strip()
    if not raw or not raw.isdigit():
        raise ChatServiceError(404, "conversation or message not found")
    n = int(raw)
    if n <= 0:
        raise ChatServiceError(404, "conversation or message not found")
    return n


_VOCE_STORAGE_PATH_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}/[0-9a-fA-F-]{16,}$")


def _looks_like_voce_storage_path(value: str) -> bool:
    return bool(_VOCE_STORAGE_PATH_RE.match(value.strip()))


def build_voce_edit_reply_body(
    *,
    json_text: str | None,
    raw_body: bytes | None,
    content_type_header: str | None,
) -> tuple[bytes, str]:
    """Shared by DM and group message edit/reply routes (VoceChat content-type rules)."""
    if json_text is not None:
        text = _require_non_empty_body(json_text)
        return text.encode("utf-8"), "text/plain; charset=utf-8"
    if raw_body is None or content_type_header is None:
        raise ChatServiceError(400, "invalid request to chat backend")
    main = _message_main_mime(content_type_header)
    if main not in _VOCE_MESSAGE_EDIT_MIMES:
        raise ChatServiceError(415, "unsupported media type for message body")
    if main in ("text/plain", "text/markdown"):
        if not raw_body.strip():
            raise ChatServiceError(400, "body must not be empty")
    elif not raw_body:
        raise ChatServiceError(400, "body must not be empty")
    if main == "vocechat/file":
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ChatServiceError(400, "invalid vocechat/file JSON body") from None
        if not isinstance(parsed, dict) or "path" not in parsed:
            raise ChatServiceError(
                400, "vocechat/file body must be a JSON object with path"
            )
    outbound = _voce_outbound_content_type(content_type_header, main)
    return raw_body, outbound


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # VoceChat sometimes uses epoch ms in other APIs; contacts use i64 ms — skip if weird
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _pick(d: dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def _contact_peer_voce_uid_str(raw: dict[str, Any]) -> str | None:
    tid = raw.get("target_uid")
    if tid is None:
        return None
    try:
        return str(int(tid))
    except (TypeError, ValueError):
        return None


def _platform_peer_identities_by_voce_uids(
    db: Session, voce_uids: list[int]
) -> dict[int, tuple[str, str]]:
    """Map VoceChat numeric uid -> (display_label, public_id)."""
    if not voce_uids:
        return {}
    uid_strs = list({str(u) for u in voce_uids})
    rows = (
        db.query(UserAppMapping, User)
        .join(User, User.id == UserAppMapping.user_id)
        .filter(
            UserAppMapping.app_name == "vocechat",
            UserAppMapping.app_uid.in_(uid_strs),
        )
        .all()
    )
    out: dict[int, tuple[str, str]] = {}
    for mapping, user in rows:
        try:
            v = int(mapping.app_uid)
        except (TypeError, ValueError):
            continue
        label = (user.display_name or "").strip() or user.username
        out[v] = (label, str(user.public_id))
    return out


def _detail_text_body(detail: dict[str, Any]) -> str:
    """Extract plain text from VoceChat ``MessageDetail`` JSON (normal/reply)."""
    dtype = str(_pick(detail, "type") or "").lower()
    if dtype not in {"normal", "reply"}:
        return ""
    ct = str(_pick(detail, "content_type") or "")
    content = _pick(detail, "content")
    if content is None:
        return ""
    if isinstance(content, dict):
        return ""
    if dtype == "reply" and ct and ct != "text/plain":
        return ""
    if dtype == "normal" and ct and ct not in {"text/plain", "vocechat/file"}:
        return ""
    return str(content)


def _file_attachment_from_detail(detail: dict[str, Any]) -> MessageAttachmentOut | None:
    """Map VoceChat ``vocechat/file`` normal message detail to platform attachment DTO."""
    dtype = str(_pick(detail, "type") or "").lower()
    if dtype != "normal":
        return None
    ct = str(_pick(detail, "content_type") or "")
    props = detail.get("properties")
    if not isinstance(props, dict):
        props = {}
    content = detail.get("content")
    content_obj = content if isinstance(content, dict) else None
    name_raw = _pick(
        props,
        "name",
        "filename",
        "file_name",
        *((["name", "filename", "file_name"] if content_obj else [])),
    )
    if name_raw is None and content_obj is not None:
        name_raw = _pick(content_obj, "name", "filename", "file_name")
    name_s = str(name_raw) if name_raw is not None else None
    mime_raw = _pick(props, "content_type", "mime", "mime_type")
    if mime_raw is None and content_obj is not None:
        mime_raw = _pick(content_obj, "content_type", "mime", "mime_type")
    mime_s = str(mime_raw) if mime_raw is not None else ""
    sz_raw = _pick(props, "size", "file_size")
    if sz_raw is None and content_obj is not None:
        sz_raw = _pick(content_obj, "size", "file_size")
    try:
        size_i = int(sz_raw) if sz_raw is not None else 0
    except (TypeError, ValueError):
        size_i = 0
    if size_i < 0:
        size_i = 0
    file_path: str | None = None
    if isinstance(content, dict):
        p = _pick(content, "path", "file_path")
        if p is not None:
            path_s = str(p).strip()
            if path_s and _looks_like_voce_storage_path(path_s):
                file_path = path_s
    elif isinstance(content, str):
        raw = content.strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                p = _pick(parsed, "path", "file_path")
                if p is not None:
                    path_s = str(p).strip()
                    if path_s and _looks_like_voce_storage_path(path_s):
                        file_path = path_s
            if not file_path and _looks_like_voce_storage_path(raw):
                file_path = raw
    if not file_path:
        p2 = _pick(props, "path", "file_path")
        if p2 is not None:
            path_s = str(p2).strip()
            if path_s and _looks_like_voce_storage_path(path_s):
                file_path = path_s
    # Treat as file only when a valid VoceChat storage path exists.
    if not file_path:
        return None
    if not mime_s:
        if ct and ct != "vocechat/file":
            mime_s = ct
        else:
            mime_s = "application/octet-stream"
    return MessageAttachmentOut(
        filename=name_s,
        content_type=mime_s,
        size=size_i,
        file_path=file_path,
    )


def _vc_message_to_dto(raw: dict[str, Any]) -> MessageOut | None:
    mid = raw.get("mid")
    if mid is None:
        return None
    payload = raw.get("payload")
    from_uid = raw.get("from_uid")
    if from_uid is None and isinstance(payload, dict):
        from_uid = payload.get("from_uid")
    if from_uid is None:
        return None
    created_raw = raw.get("created_at")
    if created_raw is None and isinstance(payload, dict):
        created_raw = payload.get("created_at")
    created = _parse_ts(created_raw) or datetime.now(timezone.utc)
    detail = raw.get("detail")
    if not isinstance(detail, dict) and isinstance(payload, dict):
        detail = payload.get("detail")
    if not isinstance(detail, dict):
        # Some VoceChat responses expose message fields at top-level/payload
        # instead of nested ``detail``.
        ct_alt = _pick(raw, "content_type")
        if ct_alt is None and isinstance(payload, dict):
            ct_alt = _pick(payload, "content_type")
        content_alt = _pick(raw, "content")
        if content_alt is None and isinstance(payload, dict):
            content_alt = _pick(payload, "content")
        props_alt = _pick(raw, "properties")
        if props_alt is None and isinstance(payload, dict):
            props_alt = _pick(payload, "properties")
        type_alt = _pick(raw, "type")
        if type_alt is None and isinstance(payload, dict):
            type_alt = _pick(payload, "type")
        if ct_alt is not None or content_alt is not None:
            detail = {
                "type": str(type_alt or "normal"),
                "content_type": str(ct_alt or ""),
                "content": content_alt,
                "properties": props_alt if isinstance(props_alt, dict) else {},
            }
    kind: Literal["text", "file"] = "text"
    attachment: MessageAttachmentOut | None = None
    body = ""
    if isinstance(detail, dict):
        attachment = _file_attachment_from_detail(detail)
        if attachment is not None:
            kind = "file"
            body = attachment.filename or attachment.file_path or ""
        else:
            body = _detail_text_body(detail)
    return MessageOut(
        id=str(int(mid)),
        body=body,
        sender_id=str(int(from_uid)),
        created_at=created,
        kind=kind,
        attachment=attachment,
    )


def _favorite_archive_out(raw: dict[str, Any]) -> FavoriteArchiveOut | None:
    fid = raw.get("id")
    if fid is None:
        return None
    cat = raw.get("created_at")
    if not isinstance(cat, int):
        return None
    return FavoriteArchiveOut(id=str(fid), created_at=int(cat))


def _map_vc_error(exc: VoceChatClientError) -> ChatServiceError:
    if exc.transport:
        return ChatServiceError(503, "chat backend unavailable")
    code = exc.http_status
    if code == 404:
        return ChatServiceError(404, "conversation or message not found")
    if code == 403:
        return ChatServiceError(403, "forbidden")
    if code == 401:
        return ChatServiceError(401, "chat authentication failed")
    if code == 400:
        return ChatServiceError(400, "invalid request to chat backend")
    if code == 413:
        return ChatServiceError(413, "attachment too large")
    if code == 429:
        return ChatServiceError(429, "too many favorite archives")
    if code is not None and code >= 500:
        return ChatServiceError(503, "chat backend error")
    return ChatServiceError(503, "chat backend error")


def _map_vc_public_resource_error(exc: VoceChatClientError) -> ChatServiceError:
    """Map VoceChat errors for unauthenticated ``/resource/*`` GET proxies."""
    if exc.transport:
        return ChatServiceError(503, "chat backend unavailable")
    code = exc.http_status
    if code == 404:
        return ChatServiceError(404, "resource not found")
    if code == 403:
        return ChatServiceError(403, "forbidden")
    if code == 401:
        return ChatServiceError(401, "chat authentication failed")
    if code == 400:
        return ChatServiceError(400, "invalid request to chat backend")
    if code == 416:
        return ChatServiceError(416, "range not satisfiable")
    if code == 405:
        return ChatServiceError(502, "chat backend does not support this operation")
    if code is not None and code >= 500:
        return ChatServiceError(503, "chat backend error")
    return ChatServiceError(503, "chat backend error")


_RESOURCE_FILE_FORWARD_HEADERS = frozenset(
    {
        "if-none-match",
        "if-modified-since",
        "range",
        "if-range",
    }
)


def _resource_file_forward_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _RESOURCE_FILE_FORWARD_HEADERS:
            out[key] = value
    return out


def _safe_client_content_disposition(raw: str | None) -> str | None:
    if not raw:
        return None
    if is_safe_content_disposition_value(raw):
        return raw
    return 'attachment; filename="attachment"'


def _filter_latin1_response_headers(headers: dict[str, str]) -> dict[str, str]:
    """Starlette response headers must be latin-1 encodable."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        try:
            str(v).encode("latin-1")
        except UnicodeEncodeError:
            continue
        out[k] = v
    return out


def _proxy_httpx_stream(
    stream_cm: Any,
) -> Response:
    """Turn an ``httpx`` stream context manager into a Starlette ``Response``."""
    resp = stream_cm.__enter__()
    try:
        if resp.status_code >= 400:
            resp.read()
            raise VoceChatClientError(
                "downstream resource error",
                http_status=resp.status_code,
            )
        out_headers = filter_allowlisted_proxy_response_headers(resp.headers)
        safe_cd = _safe_client_content_disposition(out_headers.get("content-disposition"))
        if safe_cd is None:
            out_headers.pop("content-disposition", None)
        else:
            out_headers["content-disposition"] = safe_cd
        out_headers = _filter_latin1_response_headers(out_headers)
        if resp.status_code in (204, 304):
            resp.read()
            stream_cm.__exit__(None, None, None)
            return Response(status_code=resp.status_code, headers=out_headers)
        media_type = resp.headers.get("content-type")

        def gen():
            try:
                for chunk in resp.iter_bytes():
                    yield chunk
            finally:
                stream_cm.__exit__(None, None, None)

        return StreamingResponse(
            gen(),
            status_code=resp.status_code,
            media_type=media_type,
            headers=out_headers,
        )
    except BaseException:
        if not stream_cm.__exit__(*sys.exc_info()):
            raise
        raise


class ChatService:
    def _vocechat_mapping_row(self, db: Session, user: User) -> UserAppMapping:
        row = (
            db.query(UserAppMapping)
            .filter(
                UserAppMapping.user_id == user.id,
                UserAppMapping.app_name == "vocechat",
            )
            .first()
        )
        if row is None:
            raise ChatServiceError(404, "vocechat account not linked")
        return row

    def _resolve_acting(self, mapping: UserAppMapping) -> tuple[str, int]:
        try:
            header = vocechat_acting_uid_header_value(mapping.app_uid)
            numeric = vocechat_numeric_user_id(mapping.app_uid)
        except VoceChatAppUidError:
            log.warning("Invalid vocechat app_uid for mapping id=%s", mapping.id)
            raise ChatServiceError(404, "vocechat account not linked") from None
        return header, numeric

    def _parse_peer_uid(self, conversation_id: str) -> int:
        raw = conversation_id.strip()
        if not raw or not raw.isdigit():
            raise ChatServiceError(404, "conversation or message not found")
        n = int(raw)
        if n <= 0:
            raise ChatServiceError(404, "conversation or message not found")
        return n

    def _peer_uid_from_target_public_id(
        self,
        db: Session,
        user: User,
        key: str,
        *,
        self_action_detail: str,
    ) -> tuple[int, User]:
        """Resolve VoceChat uid for a peer given ``users.public_id`` (DM / pin targets)."""
        target_user = db.query(User).filter(User.public_id == key).first()
        if target_user is None:
            raise ChatServiceError(404, "user not found")
        if target_user.id == user.id:
            raise ChatServiceError(400, self_action_detail)
        target_mapping = (
            db.query(UserAppMapping)
            .filter(
                UserAppMapping.user_id == target_user.id,
                UserAppMapping.app_name == "vocechat",
            )
            .first()
        )
        if target_mapping is None:
            raise ChatServiceError(404, "user not found")
        try:
            peer_uid = vocechat_numeric_user_id(target_mapping.app_uid)
        except VoceChatAppUidError:
            log.warning(
                "Invalid vocechat app_uid for target mapping id=%s",
                target_mapping.id,
            )
            raise ChatServiceError(404, "user not found") from None
        return peer_uid, target_user

    def _resolve_pin_peer_uid(
        self,
        db: Session,
        user: User,
        *,
        conversation_id: str | None,
        target_public_id: str | None,
    ) -> int:
        if conversation_id is not None:
            return self._parse_peer_uid(conversation_id)
        assert target_public_id is not None
        peer_uid, _tu = self._peer_uid_from_target_public_id(
            db,
            user,
            target_public_id,
            self_action_detail="cannot pin chat with yourself",
        )
        return peer_uid

    def list_conversations(
        self, db: Session, user: User, client: VoceChatClient
    ) -> ConversationListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw_list = client.list_contacts(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        peer_uids: list[int] = []
        for raw in raw_list:
            tid_s = _contact_peer_voce_uid_str(raw)
            if tid_s is not None:
                peer_uids.append(int(tid_s))
        identities = _platform_peer_identities_by_voce_uids(db, peer_uids)
        items: list[ConversationOut] = []
        for raw in raw_list:
            tid_s = _contact_peer_voce_uid_str(raw)
            if tid_s is None:
                continue
            uid_int = int(tid_s)
            identity = identities.get(uid_int)
            items.append(
                ConversationOut(
                    id=tid_s,
                    type="direct",
                    peer_display_name=identity[0] if identity else None,
                    peer_public_id=identity[1] if identity else None,
                )
            )
        return ConversationListResponse(items=items)

    def list_messages(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> MessageListResponse:
        peer = self._parse_peer_uid(conversation_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw_msgs = client.get_dm_history(
                acting_uid,
                peer,
                before_message_id=before_message_id,
                limit=limit,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        out: list[MessageOut] = []
        for raw in raw_msgs:
            dto = _vc_message_to_dto(raw)
            if dto is not None:
                out.append(dto)
        return MessageListResponse(items=out)

    def send_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        body: str,
    ) -> MessageOut:
        text = _require_non_empty_body(body)
        peer = self._parse_peer_uid(conversation_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        try:
            mid = client.send_dm_text(acting_uid, peer, text)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        now = datetime.now(timezone.utc)
        return MessageOut(
            id=str(int(mid)),
            body=text,
            sender_id=str(self_uid),
            created_at=now,
            kind="text",
            attachment=None,
        )

    def send_message_file(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        *,
        data: bytes,
        filename: str | None,
        content_type: str | None,
    ) -> MessageOut:
        """Multipart ``file`` part: upload to VoceChat storage, then ``vocechat/file`` send."""
        if not data:
            raise ChatServiceError(400, "empty file")
        if len(data) > _MAX_DM_FILE_BYTES:
            raise ChatServiceError(413, "attachment too large")
        peer = self._parse_peer_uid(conversation_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        safe_name = (filename or "").strip() or None
        mime = (content_type or "").strip() or None
        try:
            upload = client.upload_file_complete(
                acting_uid,
                data,
                content_type=mime,
                filename=safe_name,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        storage_path = str(upload.get("path", "")).strip()
        if not storage_path:
            raise ChatServiceError(503, "chat backend error")
        reported_size = upload.get("size")
        try:
            size_out = int(reported_size) if reported_size is not None else len(data)
        except (TypeError, ValueError):
            size_out = len(data)
        if size_out < 0:
            size_out = len(data)
        try:
            mid = client.send_dm_file(acting_uid, peer, storage_path)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        now = datetime.now(timezone.utc)
        att_mime = mime or "application/octet-stream"
        return MessageOut(
            id=str(int(mid)),
            body=safe_name or "",
            sender_id=str(self_uid),
            created_at=now,
            kind="file",
            attachment=MessageAttachmentOut(
                filename=safe_name,
                content_type=att_mime,
                size=size_out,
                file_path=storage_path,
            ),
        )

    def start_conversation_with_user(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        target_public_id: str,
        body: str,
    ) -> StartDirectConversationResponse:
        """module-09: send first (or next) plain-text DM to a platform user by ``public_id``."""
        text = _require_non_empty_body(body)
        key = target_public_id.strip()
        if not key:
            raise ChatServiceError(404, "user not found")

        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)

        peer_uid, target_user = self._peer_uid_from_target_public_id(
            db,
            user,
            key,
            self_action_detail="cannot message yourself",
        )

        if peer_uid == self_uid:
            raise ChatServiceError(400, "cannot message yourself")

        try:
            mid = client.send_dm_text(acting_uid, peer_uid, text)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

        peer_label = (target_user.display_name or "").strip() or target_user.username
        now = datetime.now(timezone.utc)
        return StartDirectConversationResponse(
            conversation=ConversationOut(
                id=str(peer_uid),
                type="direct",
                peer_display_name=peer_label,
                peer_public_id=str(target_user.public_id),
            ),
            message=MessageOut(
                id=str(int(mid)),
                body=text,
                sender_id=str(self_uid),
                created_at=now,
                kind="text",
                attachment=None,
            ),
        )

    def edit_conversation_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        message_id: str,
        *,
        json_text: str | None = None,
        raw_body: bytes | None = None,
        content_type_header: str | None = None,
        x_properties: str | None = None,
    ) -> int:
        """VoceChat ``PUT /message/{{mid}}/edit`` under the caller's acting token."""
        self._parse_peer_uid(conversation_id)
        mid = _parse_voce_message_id(message_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        payload, ct = build_voce_edit_reply_body(
            json_text=json_text,
            raw_body=raw_body,
            content_type_header=content_type_header,
        )
        try:
            return client.message_edit(
                acting_uid,
                mid,
                raw_body=payload,
                content_type=ct,
                x_properties=x_properties,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def like_conversation_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        message_id: str,
        *,
        action: str,
    ) -> int:
        self._parse_peer_uid(conversation_id)
        mid = _parse_voce_message_id(message_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        act = (action or "").strip()
        if not act:
            raise ChatServiceError(400, "action must not be empty")
        try:
            return client.message_like(acting_uid, mid, action=act)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def delete_conversation_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        message_id: str,
    ) -> int:
        self._parse_peer_uid(conversation_id)
        mid = _parse_voce_message_id(message_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.message_delete(acting_uid, mid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def reply_conversation_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        message_id: str,
        *,
        json_text: str | None = None,
        raw_body: bytes | None = None,
        content_type_header: str | None = None,
        x_properties: str | None = None,
    ) -> int:
        """VoceChat ``POST /message/{{mid}}/reply``."""
        self._parse_peer_uid(conversation_id)
        mid = _parse_voce_message_id(message_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        payload, ct = build_voce_edit_reply_body(
            json_text=json_text,
            raw_body=raw_body,
            content_type_header=content_type_header,
        )
        try:
            return client.message_reply(
                acting_uid,
                mid,
                raw_body=payload,
                content_type=ct,
                x_properties=x_properties,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def mark_conversation_read(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        conversation_id: str,
        last_message_id: int,
    ) -> None:
        """Maps to VoceChat ``POST /user/read-index`` with a single DM peer cursor."""
        peer = self._parse_peer_uid(conversation_id)
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.update_read_index(
                acting_uid,
                users=[{"uid": int(peer), "mid": int(last_message_id)}],
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def pin_chat(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        conversation_id: str | None,
        target_public_id: str | None,
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer_uid = self._resolve_pin_peer_uid(
            db,
            user,
            conversation_id=conversation_id,
            target_public_id=target_public_id,
        )
        if peer_uid == self_uid:
            raise ChatServiceError(400, "cannot pin chat with yourself")
        try:
            client.pin_chat(acting_uid, dm_peer_uid=peer_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def unpin_chat(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        conversation_id: str | None,
        target_public_id: str | None,
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer_uid = self._resolve_pin_peer_uid(
            db,
            user,
            conversation_id=conversation_id,
            target_public_id=target_public_id,
        )
        if peer_uid == self_uid:
            raise ChatServiceError(400, "cannot pin chat with yourself")
        try:
            client.unpin_chat(acting_uid, dm_peer_uid=peer_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def resolve_events_acting_uid(self, db: Session, user: User) -> str:
        """VoceChat ``X-Acting-Uid`` value for the current user's linked VoceChat account."""
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        return acting_uid

    def invalidate_vocechat_session(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
    ) -> None:
        """Maps to VoceChat ``POST /user/logout`` for the caller's acting-uid token.

        Disconnects the downstream chat session / SSE device for this token only.
        Does not revoke mid-auth sessions or remove the VoceChat account link.
        """
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.user_logout(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def delete_vocechat_account(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        confirm: str,
    ) -> None:
        """VoceChat ``DELETE /user/delete`` then unlink ``user_app_mappings`` vocechat row."""
        if confirm != "delete":
            raise ChatServiceError(400, 'confirm must be exactly "delete"')

        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.delete_current_user(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

        db.query(UserAppMapping).filter(UserAppMapping.id == mapping.id).delete()
        db.commit()

    def proxy_chat_resource_file(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        request: Request,
        *,
        file_path: str,
        thumbnail: bool,
        download: bool,
    ) -> Response:
        fp = file_path.strip()
        if not fp:
            raise ChatServiceError(400, "file_path is required")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        fwd = _resource_file_forward_headers(request)
        stream_cm = client.stream_resource_file_get(
            acting_uid,
            file_path=fp,
            thumbnail=thumbnail,
            download=download,
            forward_headers=fwd or None,
        )
        try:
            return _proxy_httpx_stream(stream_cm)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def delete_chat_resource_file(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        file_path: str,
    ) -> None:
        fp = file_path.strip()
        if not fp:
            raise ChatServiceError(400, "file_path is required")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.delete_resource_file(acting_uid, file_path=fp)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def create_chat_message_archive(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        body: CreateMessageArchiveBody,
    ) -> str:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.create_message_archive(acting_uid, list(body.mid_list))
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def get_chat_message_archive(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        file_path: str,
    ) -> dict[str, Any]:
        fp = file_path.strip()
        if not fp:
            raise ChatServiceError(400, "file_path is required")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.get_archive_info(acting_uid, file_path=fp)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def proxy_chat_archive_attachment(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        file_path: str,
        attachment_id: int,
        download: bool,
    ) -> Response:
        fp = file_path.strip()
        if not fp:
            raise ChatServiceError(400, "file_path is required")
        if attachment_id < 0:
            raise ChatServiceError(400, "attachment_id must be non-negative")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        stream_cm = client.stream_resource_archive_attachment_get(
            acting_uid,
            file_path=fp,
            attachment_id=attachment_id,
            download=download,
        )
        try:
            return _proxy_httpx_stream(stream_cm)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def get_chat_open_graphic(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        target_url: str,
        accept_language: str | None,
    ) -> dict[str, Any]:
        u = target_url.strip()
        if not u:
            raise ChatServiceError(400, "url is required")
        self._vocechat_mapping_row(db, user)
        try:
            return client.get_open_graphic_parse(
                target_url=u,
                accept_language=accept_language,
            )
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def proxy_resource_group_avatar(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        request: Request,
        *,
        gid: int,
    ) -> Response:
        """Proxy VoceChat ``GET /resource/group_avatar``."""
        if gid <= 0:
            raise ChatServiceError(400, "gid must be positive")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        fwd = _resource_file_forward_headers(request)
        stream_cm = client.stream_resource_group_avatar_get(
            acting_uid, gid=gid, forward_headers=fwd or None
        )
        try:
            return _proxy_httpx_stream(stream_cm)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def proxy_resource_organization_logo(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        request: Request,
        *,
        cache_buster: int | None = None,
    ) -> Response:
        """Proxy VoceChat ``GET /resource/organization/logo`` (optional ``t`` cache buster)."""
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        fwd = _resource_file_forward_headers(request)
        stream_cm = client.stream_resource_organization_logo_get(
            acting_uid,
            cache_buster=cache_buster,
            forward_headers=fwd or None,
        )
        try:
            return _proxy_httpx_stream(stream_cm)
        except VoceChatClientError as exc:
            raise _map_vc_public_resource_error(exc) from exc

    def list_favorite_archives(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
    ) -> FavoriteListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw_list = client.list_favorite_archives(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[FavoriteArchiveOut] = []
        for raw in raw_list:
            dto = _favorite_archive_out(raw)
            if dto is not None:
                items.append(dto)
        return FavoriteListResponse(items=items)

    def create_favorite_archive(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        body: CreateFavoriteBody,
    ) -> FavoriteArchiveOut:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            raw = client.create_favorite_archive(
                acting_uid, list(body.message_ids)
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        dto = _favorite_archive_out(raw)
        if dto is None:
            raise ChatServiceError(503, "chat backend error")
        return dto

    def delete_favorite_archive(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        favorite_id: str,
    ) -> None:
        fid = favorite_id.strip()
        if not fid:
            raise ChatServiceError(404, "favorite not found")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            client.delete_favorite_archive(acting_uid, fid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def get_favorite_archive_detail(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        favorite_id: str,
    ) -> dict[str, Any]:
        fid = favorite_id.strip()
        if not fid:
            raise ChatServiceError(404, "favorite not found")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _n = self._resolve_acting(mapping)
        try:
            return client.get_favorite_archive_info(acting_uid, fid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def download_favorite_attachment(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        favorite_id: str,
        attachment_id: int,
        *,
        download: bool,
    ) -> tuple[bytes, str | None, str | None]:
        fid = favorite_id.strip()
        if not fid:
            raise ChatServiceError(404, "favorite not found")
        if attachment_id < 0:
            raise ChatServiceError(404, "favorite not found")
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        try:
            body, ct, cd = client.get_favorite_attachment_bytes(
                acting_uid,
                self_uid,
                fid,
                attachment_id,
                download=download,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        safe_cd = _safe_client_content_disposition(cd)
        return body, ct, safe_cd


chat_service = ChatService()
