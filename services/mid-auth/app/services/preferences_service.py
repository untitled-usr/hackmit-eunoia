"""Notification mute, burn-after-reading, and related preferences via VoceChat."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError
from app.models.users import User
from app.schemas.preferences import MuteRequest, UpdateBurnAfterReadingRequest
from app.services.chat_service import ChatServiceError, _map_vc_error
from app.services.social_service import social_service


def _parse_platform_group_id(group_id: str) -> int:
    """Same rules as ``GroupService._parse_group_id`` (avoid importing group_service)."""
    raw = group_id.strip()
    if not raw or not raw.isdigit():
        raise ChatServiceError(404, "group not found")
    n = int(raw)
    if n <= 0:
        raise ChatServiceError(404, "group not found")
    return n


class PreferencesService:
    def update_mute(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        payload: MuteRequest,
    ) -> None:
        acting_uid, self_uid = social_service.acting_context(db, user)

        vc_body: dict[str, Any] = {}

        add_u: list[dict[str, Any]] = []
        for item in payload.add_users:
            uid = social_service.resolve_target_voce_uid(db, item.target_public_id)
            if uid == self_uid:
                raise ChatServiceError(400, "invalid mute target")
            cell: dict[str, Any] = {"uid": uid}
            if item.expired_in is not None:
                cell["expired_in"] = item.expired_in
            add_u.append(cell)
        if add_u:
            vc_body["add_users"] = add_u

        add_g: list[dict[str, Any]] = []
        for item in payload.add_groups:
            gid = _parse_platform_group_id(item.group_id)
            cell = {"gid": gid}
            if item.expired_in is not None:
                cell["expired_in"] = item.expired_in
            add_g.append(cell)
        if add_g:
            vc_body["add_groups"] = add_g

        rm_u: list[int] = []
        for pid in payload.remove_users:
            uid = social_service.resolve_target_voce_uid(db, pid)
            if uid == self_uid:
                raise ChatServiceError(400, "invalid mute target")
            rm_u.append(uid)
        if rm_u:
            vc_body["remove_users"] = rm_u

        rm_g: list[int] = []
        for gid_s in payload.remove_groups:
            rm_g.append(_parse_platform_group_id(gid_s))
        if rm_g:
            vc_body["remove_groups"] = rm_g

        try:
            client.update_mute(acting_uid, vc_body)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def update_burn_after_reading(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        payload: UpdateBurnAfterReadingRequest,
    ) -> None:
        acting_uid, self_uid = social_service.acting_context(db, user)

        vc_users: list[dict[str, Any]] = []
        for item in payload.users:
            uid = social_service.resolve_target_voce_uid(db, item.target_public_id)
            if uid == self_uid:
                raise ChatServiceError(400, "invalid burn-after-reading peer")
            vc_users.append({"uid": uid, "expires_in": item.expires_in})

        vc_groups: list[dict[str, Any]] = []
        for item in payload.groups:
            gid = _parse_platform_group_id(item.group_id)
            vc_groups.append({"gid": gid, "expires_in": item.expires_in})

        vc_body = {"users": vc_users, "groups": vc_groups}
        try:
            client.update_burn_after_reading(acting_uid, vc_body)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc


preferences_service = PreferencesService()
