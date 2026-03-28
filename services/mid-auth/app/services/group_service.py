"""Group CRUD, members, messages via VoceChat (platform paths only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError
from app.models.users import User
from app.schemas.chat import MessageListResponse, MessageOut
from app.schemas.groups import (
    ChangeGroupTypeRequest,
    GroupCreateRequest,
    GroupCreateResponse,
    GroupListResponse,
    GroupOut,
    GroupRealtimeTokenResponse,
    GroupUpdateRequest,
)
from app.services.chat_service import (
    ChatServiceError,
    _map_vc_error,
    _parse_voce_message_id,
    _require_non_empty_body,
    _vc_message_to_dto,
    build_voce_edit_reply_body,
)
from app.services.social_service import social_service

# VoceChat ``POST /group/{gid}/send`` (same family as ``POST /user/{uid}/send``).
_GROUP_SEND_VOCE_MIME = frozenset(
    {"text/plain", "text/markdown", "vocechat/file", "vocechat/archive"}
)


def group_message_main_mime(content_type: str) -> str:
    return (content_type or "").split(";", maxsplit=1)[0].strip().lower()


def _outbound_group_content_type(incoming_header: str, main: str) -> str:
    """Ensure text/plain carries charset when missing (VoceChat OpenAPI default)."""
    h = incoming_header.strip()
    if main == "text/plain" and "charset" not in h.lower():
        return "text/plain; charset=utf-8"
    return h or main


def _platform_body_after_send(main_mime: str, raw: bytes) -> str:
    if main_mime in ("text/plain", "text/markdown"):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    return ""


class GroupService:
    @staticmethod
    def _parse_group_id(group_id: str) -> int:
        raw = group_id.strip()
        if not raw or not raw.isdigit():
            raise ChatServiceError(404, "group not found")
        n = int(raw)
        if n <= 0:
            raise ChatServiceError(404, "group not found")
        return n

    @staticmethod
    def _raw_group_to_out(raw: dict[str, Any]) -> GroupOut | None:
        gid = raw.get("gid")
        if gid is None:
            return None
        members = raw.get("members") or []
        member_strs: list[str] = []
        if isinstance(members, list):
            for m in members:
                try:
                    member_strs.append(str(int(m)))
                except (TypeError, ValueError):
                    continue
        owner = raw.get("owner")
        owner_s = str(int(owner)) if owner is not None else None
        desc = raw.get("description")
        return GroupOut(
            group_id=str(int(gid)),
            name=str(raw.get("name") or ""),
            description=str(desc) if desc is not None else None,
            owner_voce_uid=owner_s,
            is_public=bool(raw.get("is_public", False)),
            member_voce_uids=member_strs,
        )

    @staticmethod
    def _raw_agora_token_to_realtime(raw: dict[str, Any]) -> GroupRealtimeTokenResponse | None:
        """Map VoceChat Agora payload to platform DTO (no vendor path in API)."""
        try:
            tok = raw.get("agora_token")
            app_id = raw.get("app_id")
            uid = raw.get("uid")
            channel = raw.get("channel_name")
            exp = raw.get("expired_in")
            if tok is None or app_id is None or uid is None or channel is None or exp is None:
                return None
            return GroupRealtimeTokenResponse(
                token=str(tok),
                app_id=str(app_id),
                client_uid=int(uid),
                channel_name=str(channel),
                expires_in_seconds=int(exp),
            )
        except (TypeError, ValueError):
            return None

    def list_groups(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        public_only: bool | None,
    ) -> GroupListResponse:
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            raw_list = client.list_groups(acting_uid, public_only=public_only)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[GroupOut] = []
        for raw in raw_list:
            g = self._raw_group_to_out(raw)
            if g is not None:
                items.append(g)
        return GroupListResponse(items=items)

    def create_group(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        payload: GroupCreateRequest,
    ) -> GroupCreateResponse:
        acting_uid, _ = social_service.acting_context(db, user)
        member_uids: list[int] = []
        for pid in payload.initial_member_public_ids:
            member_uids.append(social_service.resolve_target_voce_uid(db, pid))
        body: dict[str, Any] = {
            "name": payload.name,
            "description": payload.description or "",
            "is_public": payload.is_public,
            "members": member_uids,
        }
        try:
            gid, created_at = client.create_group(acting_uid, body)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        return GroupCreateResponse(group_id=str(int(gid)), created_at=int(created_at))

    def get_group(
        self, db: Session, user: User, client: VoceChatClient, group_id: str
    ) -> GroupOut:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            raw = client.get_group(acting_uid, gid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        out = self._raw_group_to_out(raw)
        if out is None:
            raise ChatServiceError(404, "group not found")
        return out

    def get_realtime_token(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
    ) -> GroupRealtimeTokenResponse:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            raw = client.get_group_agora_token(acting_uid, gid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        out = self._raw_agora_token_to_realtime(raw)
        if out is None:
            raise ChatServiceError(502, "invalid realtime token response")
        return out

    def update_group(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        payload: GroupUpdateRequest,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        raw = payload.model_dump(exclude_unset=True)
        if not raw:
            raise ChatServiceError(400, "no fields to update")
        body: dict[str, Any] = {}
        if "name" in raw:
            if raw["name"] is None:
                raise ChatServiceError(400, "invalid name")
            body["name"] = raw["name"]
        if "description" in raw:
            desc = raw["description"]
            body["description"] = "" if desc is None else desc
        if "owner_public_id" in raw:
            opid = raw["owner_public_id"]
            if opid is None or not str(opid).strip():
                raise ChatServiceError(400, "invalid owner_public_id")
            body["owner"] = social_service.resolve_target_voce_uid(db, str(opid))
        try:
            client.update_group(acting_uid, gid, body)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def delete_group(
        self, db: Session, user: User, client: VoceChatClient, group_id: str
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.delete_group(acting_uid, gid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def add_members(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        target_public_ids: list[str],
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        uids: list[int] = []
        for pid in target_public_ids:
            uids.append(social_service.resolve_target_voce_uid(db, pid))
        try:
            client.group_add_members(acting_uid, gid, uids)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def remove_member(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        target_public_id: str,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        uid = social_service.resolve_target_voce_uid(db, target_public_id)
        try:
            client.group_remove_members(acting_uid, gid, [uid])
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def change_group_type(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        payload: ChangeGroupTypeRequest,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        member_uids: list[int] = []
        for pid in payload.member_public_ids:
            member_uids.append(social_service.resolve_target_voce_uid(db, pid))
        try:
            client.group_change_type(
                acting_uid,
                gid,
                is_public=payload.is_public,
                members=member_uids,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def leave_group(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.leave_group(acting_uid, gid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def send_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        body: str,
    ) -> MessageOut:
        text = _require_non_empty_body(body)
        gid = self._parse_group_id(group_id)
        acting_uid, self_uid = social_service.acting_context(db, user)
        try:
            mid = client.send_group_text(acting_uid, gid, text)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        now = datetime.now(timezone.utc)
        return MessageOut(
            id=str(int(mid)),
            body=text,
            sender_id=str(self_uid),
            created_at=now,
        )

    def send_message_voce_payload(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        *,
        raw_body: bytes,
        content_type_header: str,
        x_properties: str | None,
    ) -> MessageOut:
        """Non-JSON group send: forward body and Content-Type to VoceChat."""
        main = group_message_main_mime(content_type_header)
        if main not in _GROUP_SEND_VOCE_MIME:
            raise ChatServiceError(415, "unsupported media type for group message")
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
        gid = self._parse_group_id(group_id)
        acting_uid, self_uid = social_service.acting_context(db, user)
        outbound_ct = _outbound_group_content_type(content_type_header, main)
        try:
            mid = client.send_group_payload(
                acting_uid,
                gid,
                raw_body=raw_body,
                content_type=outbound_ct,
                x_properties=x_properties,
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        now = datetime.now(timezone.utc)
        return MessageOut(
            id=str(int(mid)),
            body=_platform_body_after_send(main, raw_body),
            sender_id=str(self_uid),
            created_at=now,
        )

    def list_messages(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> MessageListResponse:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            raw_msgs = client.get_group_history(
                acting_uid,
                gid,
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

    def mark_group_read(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        last_message_id: int,
    ) -> None:
        """Maps to VoceChat ``POST /user/read-index`` with a single group cursor."""
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.update_read_index(
                acting_uid,
                groups=[{"gid": int(gid), "mid": int(last_message_id)}],
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def pin_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: int,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.group_pin_message(acting_uid, gid, int(message_id))
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def unpin_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: int,
    ) -> None:
        gid = self._parse_group_id(group_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.group_unpin_message(acting_uid, gid, int(message_id))
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def edit_group_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: str,
        *,
        json_text: str | None = None,
        raw_body: bytes | None = None,
        content_type_header: str | None = None,
        x_properties: str | None = None,
    ) -> int:
        self._parse_group_id(group_id)
        mid = _parse_voce_message_id(message_id)
        acting_uid, _ = social_service.acting_context(db, user)
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

    def like_group_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: str,
        *,
        action: str,
    ) -> int:
        self._parse_group_id(group_id)
        mid = _parse_voce_message_id(message_id)
        acting_uid, _ = social_service.acting_context(db, user)
        act = (action or "").strip()
        if not act:
            raise ChatServiceError(400, "action must not be empty")
        try:
            return client.message_like(acting_uid, mid, action=act)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def delete_group_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: str,
    ) -> int:
        self._parse_group_id(group_id)
        mid = _parse_voce_message_id(message_id)
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            return client.message_delete(acting_uid, mid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def upload_group_avatar(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        image_bytes: bytes,
    ) -> None:
        """VoceChat ``POST /group/{gid}/avatar`` (PNG body)."""
        gid = self._parse_group_id(group_id)
        if not image_bytes:
            raise ChatServiceError(400, "image body is required")
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.upload_group_avatar(acting_uid, gid, image_bytes)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def reply_group_message(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        group_id: str,
        message_id: str,
        *,
        json_text: str | None = None,
        raw_body: bytes | None = None,
        content_type_header: str | None = None,
        x_properties: str | None = None,
    ) -> int:
        self._parse_group_id(group_id)
        mid = _parse_voce_message_id(message_id)
        acting_uid, _ = social_service.acting_context(db, user)
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


group_service = GroupService()
