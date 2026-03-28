"""Registered chat devices (sessions) for the current user via VoceChat."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError
from app.models.users import User
from app.schemas.devices import UserDeviceListResponse, UserDeviceOut
from app.services.chat_service import ChatServiceError, _map_vc_error
from app.services.social_service import social_service


class DevicesService:
    def list_my_devices(
        self, db: Session, user: User, client: VoceChatClient
    ) -> UserDeviceListResponse:
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            raw = client.list_user_devices(acting_uid)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc
        items = [
            UserDeviceOut(device_id=s)
            for s in raw
            if isinstance(s, str) and s.strip() != ""
        ]
        return UserDeviceListResponse(items=items)

    def delete_my_device(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        device_id: str,
    ) -> None:
        key = device_id.strip()
        if not key:
            raise ChatServiceError(400, "device_id must not be empty")
        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.delete_user_device(acting_uid, key)
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc

    def update_push_token(
        self,
        db: Session,
        user: User,
        client: VoceChatClient,
        *,
        device_id: str,
        token: str,
    ) -> None:
        device_key = device_id.strip()
        token_value = token.strip()
        if not device_key or not token_value:
            raise ChatServiceError(400, "device_id and token must be non-empty")

        acting_uid, _ = social_service.acting_context(db, user)
        try:
            client.update_fcm_token(
                acting_uid, device_id=device_key, token=token_value
            )
        except VoceChatClientError as exc:
            raise _map_vc_error(exc) from exc


devices_service = DevicesService()
