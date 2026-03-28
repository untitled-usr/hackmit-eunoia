"""Friend requests, friends, blacklist via VoceChat (platform paths only)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError
from app.lib.vocechat_acting_uid import (
    VoceChatAppUidError,
    vocechat_acting_uid_header_value,
    vocechat_numeric_user_id,
)
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.directory import UserDirectorySearchResult
from app.schemas.social import (
    BlacklistListResponse,
    BlacklistUserOut,
    ContactActionPayload,
    ContactInfoOut,
    CreateFriendRequestPayload,
    FriendRequestCreatedResponse,
    FriendRequestItemOut,
    FriendRequestListResponse,
    FriendRequestRecordItemOut,
    FriendRequestRecordsListResponse,
    SocialUserIdentityOut,
    SocialContactListResponse,
    SocialContactOut,
)
from app.services.chat_service import ChatServiceError, _map_vc_error

log = logging.getLogger(__name__)


class SocialService:
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

    def acting_context(self, db: Session, user: User) -> tuple[str, int]:
        mapping = self._vocechat_mapping_row(db, user)
        return self._resolve_acting(mapping)

    def _resolve_user_by_identifier(self, db: Session, identifier: str) -> User:
        key = identifier.strip()
        if not key:
            raise ChatServiceError(404, "user not found")

        target_user = (
            db.query(User)
            .filter(
                or_(
                    User.public_id == key,
                    func.lower(User.email) == key.lower(),
                    User.username == key,
                )
            )
            .first()
        )
        if target_user is not None:
            return target_user

        # Secondary fallback for case-insensitive username matching.
        target_user = (
            db.query(User)
            .filter(func.lower(User.username) == key.lower())
            .first()
        )
        if target_user is None:
            raise ChatServiceError(404, "user not found")
        return target_user

    def resolve_target_voce_uid(self, db: Session, target_identifier: str) -> int:
        target_user = self._resolve_user_by_identifier(db, target_identifier)
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
            return vocechat_numeric_user_id(target_mapping.app_uid)
        except VoceChatAppUidError:
            log.warning(
                "Invalid vocechat app_uid for target mapping id=%s",
                target_mapping.id,
            )
            raise ChatServiceError(404, "user not found") from None

    def lookup_directory_user_by_public_id(
        self,
        db: Session,
        _user: User,
        *,
        public_id: str,
    ) -> UserDirectorySearchResult:
        """Resolve a platform ``public_id`` to safe directory fields (requires VoceChat link)."""
        _ = _user
        return self._directory_user_by_public_id(db, public_id)

    def search_directory_users(
        self,
        db: Session,
        _user: User,
        *,
        keyword: str,
        limit: int = 20,
    ) -> list[UserDirectorySearchResult]:
        _ = _user
        q = keyword.strip()
        if not q:
            return []
        rows = (
            db.query(User)
            .join(
                UserAppMapping,
                (UserAppMapping.user_id == User.id)
                & (UserAppMapping.app_name == "vocechat"),
            )
            .filter(
                or_(
                    User.public_id.ilike(f"%{q}%"),
                    User.username.ilike(f"%{q}%"),
                    User.email.ilike(f"%{q}%"),
                )
            )
            .limit(max(1, min(limit, 50)))
            .all()
        )
        out: list[UserDirectorySearchResult] = []
        for row in rows:
            label = (row.display_name or "").strip() or row.username
            out.append(
                UserDirectorySearchResult(
                    public_id=str(row.public_id),
                    username=row.username,
                    email=row.email,
                    display_name=label,
                    in_online=False,
                )
            )
        return out

    def _directory_user_by_public_id(
        self, db: Session, public_id: str
    ) -> UserDirectorySearchResult:
        target_user = db.query(User).filter(User.public_id == public_id).first()
        if target_user is None:
            raise ChatServiceError(404, "user not found")
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
        label = (target_user.display_name or "").strip() or target_user.username
        return UserDirectorySearchResult(
            public_id=str(target_user.public_id),
            username=target_user.username,
            email=target_user.email,
            display_name=label,
            in_online=False,
        )

    def _public_id_for_voce_uid(self, db: Session, voce_uid: int) -> str | None:
        identity = self._platform_identity_for_voce_uid(db, voce_uid)
        if identity is None:
            return None
        return identity[0]

    def _platform_identity_for_voce_uid(
        self, db: Session, voce_uid: int
    ) -> tuple[str, str, str | None] | None:
        row = (
            db.query(UserAppMapping, User)
            .join(User, User.id == UserAppMapping.user_id)
            .filter(
                UserAppMapping.app_name == "vocechat",
                UserAppMapping.app_uid == str(int(voce_uid)),
            )
            .first()
        )
        if row is None:
            return None
        _mapping, user = row
        label = (user.display_name or "").strip() or user.username or str(user.public_id)
        avatar_url = None
        if (
            user.avatar_data
            and user.avatar_mime_type
            and user.avatar_updated_at is not None
        ):
            t = int(user.avatar_updated_at.timestamp())
            avatar_url = f"/me/directory/users/{user.public_id}/avatar?t={t}"
        return str(user.public_id), label, avatar_url

    def _identity_for_voce_uid(
        self, db: Session, voce_uid: int
    ) -> SocialUserIdentityOut | None:
        row = (
            db.query(UserAppMapping, User)
            .join(User, User.id == UserAppMapping.user_id)
            .filter(
                UserAppMapping.app_name == "vocechat",
                UserAppMapping.app_uid == str(int(voce_uid)),
            )
            .first()
        )
        if row is None:
            return None
        _mapping, user = row
        display_name = (user.display_name or "").strip() or user.username
        return SocialUserIdentityOut(
            public_id=str(user.public_id),
            username=user.username,
            email=user.email,
            display_name=display_name,
        )

    @staticmethod
    def _contact_info_out(raw: dict[str, Any]) -> ContactInfoOut:
        ci = raw if isinstance(raw, dict) else {}
        remark_v = ci.get("remark")
        remark_s = str(remark_v) if remark_v is not None else ""
        rb = ci.get("removed_by_peer")
        removed = bool(rb) if rb is not None else False
        ca = ci.get("created_at")
        ua = ci.get("updated_at")
        return ContactInfoOut(
            status=str(ci.get("status") or ""),
            created_at=int(ca) if ca is not None else 0,
            updated_at=int(ua) if ua is not None else 0,
            removed_by_peer=removed,
            remark=remark_s,
        )

    def _raw_contact_to_out(
        self, db: Session, raw: dict[str, Any]
    ) -> SocialContactOut | None:
        tid = raw.get("target_uid")
        if tid is None:
            return None
        try:
            voce_tid = int(tid)
        except (TypeError, ValueError):
            return None
        platform_identity = self._platform_identity_for_voce_uid(db, voce_tid)
        if platform_identity is None:
            return None
        public_id, platform_display_name, avatar_url = platform_identity
        cinfo_raw = raw.get("contact_info")
        if not isinstance(cinfo_raw, dict):
            cinfo_raw = {}
        return SocialContactOut(
            target_public_id=public_id,
            conversation_id=str(voce_tid),
            # Prefer platform display_name to avoid VoceChat-side stale/nickname divergence.
            display_name=platform_display_name,
            avatar_url=avatar_url,
            contact_info=self._contact_info_out(cinfo_raw),
        )

    def list_social_contacts(
        self, db: Session, user: User, client: VoceChatClient
    ) -> SocialContactListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            raw_list = client.list_contacts(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[SocialContactOut] = []
        for raw in raw_list:
            dto = self._raw_contact_to_out(db, raw)
            if dto is not None:
                items.append(dto)
        return SocialContactListResponse(items=items)

    def get_social_contact(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        target_public_id: str,
    ) -> SocialContactOut:
        key = target_public_id.strip()
        if not key:
            raise ChatServiceError(404, "contact not found")
        listing = self.list_social_contacts(db, user, client)
        for item in listing.items:
            if item.target_public_id == key:
                return item
        raise ChatServiceError(404, "contact not found")

    def patch_contact_remark(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        target_public_id: str,
        remark: str,
    ) -> SocialContactOut:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(db, target_public_id)
        if peer == self_uid:
            raise ChatServiceError(400, "invalid target")
        try:
            client.put_contact_remark(acting_uid, target_uid=peer, remark=remark)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        return self.get_social_contact(db, user, client, target_public_id)

    @staticmethod
    def _friend_request_view_to_data(raw: dict[str, Any]) -> dict[str, Any] | None:
        rid = raw.get("id")
        ru = raw.get("requester_uid")
        rv = raw.get("receiver_uid")
        if rid is None or ru is None or rv is None:
            return None
        created = raw.get("created_at")
        if created is None:
            created_s = ""
        elif isinstance(created, (int, float)):
            created_s = str(int(created))
        else:
            created_s = str(created)
        return {
            "id": str(int(rid)),
            "requester_uid": int(ru),
            "receiver_uid": int(rv),
            "message": str(raw.get("message") or ""),
            "status": str(raw.get("status") or ""),
            "created_at": created_s,
        }

    @staticmethod
    def _friend_request_record_view_to_data(raw: dict[str, Any]) -> dict[str, Any] | None:
        base = SocialService._friend_request_view_to_data(raw)
        if base is None:
            return None
        ra = raw.get("responded_at")
        if ra is None:
            responded_s = "0"
        elif isinstance(ra, (int, float)):
            responded_s = str(int(ra))
        else:
            responded_s = str(ra)
        cd = raw.get("can_delete")
        if isinstance(cd, bool):
            can_del = cd
        elif cd is None:
            can_del = False
        else:
            can_del = bool(cd)
        return {
            "id": base["id"],
            "requester_uid": base["requester_uid"],
            "receiver_uid": base["receiver_uid"],
            "message": base["message"],
            "status": base["status"],
            "created_at": base["created_at"],
            "responded_at": responded_s,
            "can_delete": can_del,
        }

    def _user_info_to_blacklist(
        self, db: Session, raw: dict[str, Any]
    ) -> BlacklistUserOut | None:
        uid = raw.get("uid")
        if uid is None:
            return None
        try:
            voce_uid = int(uid)
        except (TypeError, ValueError):
            return None
        identity = self._platform_identity_for_voce_uid(db, voce_uid)
        target_public_id = identity[0] if identity else None
        display_name = identity[1] if identity else None
        avatar_url = identity[2] if identity else None
        return BlacklistUserOut(
            voce_uid=str(voce_uid),
            name=str(raw.get("name") or ""),
            target_public_id=target_public_id,
            display_name=display_name,
            avatar_url=avatar_url,
        )

    def create_friend_request(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        payload: CreateFriendRequestPayload,
    ) -> FriendRequestCreatedResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(
            db, payload.resolved_target_identifier()
        )
        if peer == self_uid:
            raise ChatServiceError(400, "invalid friend request target")
        try:
            rid = client.create_friend_request(
                acting_uid, peer, message=payload.message or ""
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        return FriendRequestCreatedResponse(request_id=str(int(rid)))

    def list_incoming_friend_requests(
        self, db: Session, user: User, client: VoceChatClient
    ) -> FriendRequestListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            raw_list = client.list_friend_requests_incoming(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[FriendRequestItemOut] = []
        for raw in raw_list:
            data = self._friend_request_view_to_data(raw)
            if data is None:
                continue
            items.append(
                FriendRequestItemOut(
                    id=data["id"],
                    requester=self._identity_for_voce_uid(db, data["requester_uid"]),
                    receiver=self._identity_for_voce_uid(db, data["receiver_uid"]),
                    requester_voce_uid=str(data["requester_uid"]),
                    receiver_voce_uid=str(data["receiver_uid"]),
                    message=data["message"],
                    status=data["status"],
                    created_at=data["created_at"],
                )
            )
        return FriendRequestListResponse(items=items)

    def list_outgoing_friend_requests(
        self, db: Session, user: User, client: VoceChatClient
    ) -> FriendRequestListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            raw_list = client.list_friend_requests_outgoing(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[FriendRequestItemOut] = []
        for raw in raw_list:
            data = self._friend_request_view_to_data(raw)
            if data is None:
                continue
            items.append(
                FriendRequestItemOut(
                    id=data["id"],
                    requester=self._identity_for_voce_uid(db, data["requester_uid"]),
                    receiver=self._identity_for_voce_uid(db, data["receiver_uid"]),
                    requester_voce_uid=str(data["requester_uid"]),
                    receiver_voce_uid=str(data["receiver_uid"]),
                    message=data["message"],
                    status=data["status"],
                    created_at=data["created_at"],
                )
            )
        return FriendRequestListResponse(items=items)

    def list_friend_request_records(
        self, db: Session, user: User, client: VoceChatClient
    ) -> FriendRequestRecordsListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            raw_list = client.list_friend_requests_records(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[FriendRequestRecordItemOut] = []
        for raw in raw_list:
            data = self._friend_request_record_view_to_data(raw)
            if data is None:
                continue
            items.append(
                FriendRequestRecordItemOut(
                    id=data["id"],
                    requester=self._identity_for_voce_uid(db, data["requester_uid"]),
                    receiver=self._identity_for_voce_uid(db, data["receiver_uid"]),
                    requester_voce_uid=str(data["requester_uid"]),
                    receiver_voce_uid=str(data["receiver_uid"]),
                    message=data["message"],
                    status=data["status"],
                    created_at=data["created_at"],
                    responded_at=data["responded_at"],
                    can_delete=data["can_delete"],
                )
            )
        return FriendRequestRecordsListResponse(items=items)

    def delete_friend_request_record(
        self, db: Session, user: User, client: VoceChatClient, request_id: int
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            client.delete_friend_request_record(acting_uid, request_id)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def accept_friend_request(
        self, db: Session, user: User, client: VoceChatClient, request_id: int
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            client.accept_friend_request(acting_uid, request_id)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def reject_friend_request(
        self, db: Session, user: User, client: VoceChatClient, request_id: int
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            client.reject_friend_request(acting_uid, request_id)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def cancel_friend_request(
        self, db: Session, user: User, client: VoceChatClient, request_id: int
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            client.cancel_friend_request(acting_uid, request_id)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def apply_contact_action(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        payload: ContactActionPayload,
    ) -> None:
        """VoceChat legacy POST /user/update_contact_status (add/remove/block/unblock)."""
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(
            db, payload.resolved_target_identifier()
        )
        if peer == self_uid:
            raise ChatServiceError(400, "invalid target")
        try:
            client.update_contact_status(acting_uid, peer, payload.action)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def remove_friend(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        target_public_id: str,
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(db, target_public_id)
        if peer == self_uid:
            raise ChatServiceError(400, "invalid target")
        try:
            client.delete_friend(acting_uid, peer)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def list_blacklist(
        self, db: Session, user: User, client: VoceChatClient
    ) -> BlacklistListResponse:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, _ = self._resolve_acting(mapping)
        try:
            raw_list = client.list_blacklist(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items: list[BlacklistUserOut] = []
        for raw in raw_list:
            dto = self._user_info_to_blacklist(db, raw)
            if dto is not None:
                items.append(dto)
        return BlacklistListResponse(items=items)

    def add_blacklist(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        target_public_id: str,
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(db, target_public_id)
        if peer == self_uid:
            raise ChatServiceError(400, "invalid target")
        try:
            client.add_blacklist(acting_uid, peer)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def remove_blacklist(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        target_public_id: str,
    ) -> None:
        mapping = self._vocechat_mapping_row(db, user)
        acting_uid, self_uid = self._resolve_acting(mapping)
        peer = self.resolve_target_voce_uid(db, target_public_id)
        if peer == self_uid:
            raise ChatServiceError(400, "invalid target")
        try:
            client.remove_blacklist(acting_uid, peer)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc


social_service = SocialService()
