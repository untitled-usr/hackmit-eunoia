from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from fastapi import HTTPException

from mid_auth_admin.core.platform_settings import (
    FIXED_ACTING_UID,
    PROTECTED_ADMIN_USER_IDS,
    get_platform_settings,
)
from mid_auth_admin.integrations.memos_admin_client import MemosAdminClient
from mid_auth_admin.integrations.openwebui_admin_client import OpenWebUIAdminClient
from mid_auth_admin.integrations.platform_client_base import (
    DownstreamHttpError,
    PlatformActionNotSupported,
    PlatformClientBase,
)
from mid_auth_admin.integrations.vocechat_admin_client import VoceChatAdminClient
from mid_auth_admin.schemas.platform_users import (
    PlatformName,
    PlatformUserCreateRequest,
    PlatformUserListResponse,
    PlatformUserPatchRequest,
    PlatformUserRecord,
)


@dataclass
class PlatformUserAdminService:
    vocechat: PlatformClientBase
    memos: PlatformClientBase
    openwebui: PlatformClientBase

    @staticmethod
    def build() -> "PlatformUserAdminService":
        settings = get_platform_settings()
        if not settings.vocechat_base_url or not settings.memos_base_url or not settings.openwebui_base_url:
            raise HTTPException(
                status_code=503,
                detail=(
                    "One or more downstream base URLs are missing. "
                    "Require MID_AUTH_VOCECHAT_BASE_URL, MID_AUTH_MEMOS_BASE_URL, MID_AUTH_OPEN_WEBUI_BASE_URL."
                ),
            )
        return PlatformUserAdminService(
            vocechat=VoceChatAdminClient(
                platform="vocechat",
                base_url=settings.vocechat_base_url,
                acting_uid_header=settings.acting_uid_header,
                acting_uid_value=FIXED_ACTING_UID["vocechat"],
            ),
            memos=MemosAdminClient(
                platform="memos",
                base_url=settings.memos_base_url,
                acting_uid_header=settings.acting_uid_header,
                acting_uid_value=FIXED_ACTING_UID["memos"],
            ),
            openwebui=OpenWebUIAdminClient(
                platform="openwebui",
                base_url=settings.openwebui_base_url,
                acting_uid_header=settings.acting_uid_header,
                acting_uid_value=FIXED_ACTING_UID["openwebui"],
            ),
        )

    def _client(self, platform: PlatformName) -> PlatformClientBase:
        return getattr(self, platform)

    @staticmethod
    def _normalize_user_id(platform: PlatformName, user_id: str) -> str:
        normalized = user_id.strip()
        if platform == "memos" and normalized.startswith("users/"):
            return normalized.split("/", 1)[1]
        return normalized

    @staticmethod
    def _map_exception(exc: Exception) -> None:
        if isinstance(exc, PlatformActionNotSupported):
            raise HTTPException(status_code=501, detail=str(exc))
        if isinstance(exc, DownstreamHttpError):
            raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)
        raise exc

    def list_users(
        self, *, platform: PlatformName, q: str | None, limit: int, offset: int
    ) -> PlatformUserListResponse:
        try:
            rows = self._client(platform).list_users(q=q, limit=limit, offset=offset)
        except Exception as exc:  # noqa: BLE001
            self._map_exception(exc)
            raise
        return PlatformUserListResponse(platform=platform, limit=limit, offset=offset, items=rows)

    def get_user(self, *, platform: PlatformName, user_id: str) -> PlatformUserRecord:
        uid = self._normalize_user_id(platform, user_id)
        try:
            return self._client(platform).get_user(user_id=uid)
        except Exception as exc:  # noqa: BLE001
            self._map_exception(exc)
            raise

    def create_user(
        self, *, platform: PlatformName, payload: PlatformUserCreateRequest
    ) -> PlatformUserRecord:
        try:
            return self._client(platform).create_user(payload=payload)
        except Exception as exc:  # noqa: BLE001
            self._map_exception(exc)
            raise

    def update_user(
        self, *, platform: PlatformName, user_id: str, payload: PlatformUserPatchRequest
    ) -> PlatformUserRecord:
        uid = self._normalize_user_id(platform, user_id)
        client = self._client(platform)
        has_profile_update = any(
            v is not None for v in [payload.display_name, payload.email, payload.password]
        ) or bool(payload.raw)
        try:
            if has_profile_update:
                record = client.update_user_profile(user_id=uid, payload=payload)
                if payload.is_active is not None:
                    record = client.set_user_enabled(user_id=uid, enabled=payload.is_active)
                return record
            if payload.is_active is not None:
                return client.set_user_enabled(user_id=uid, enabled=payload.is_active)
            raise HTTPException(status_code=422, detail="PATCH payload is empty")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            self._map_exception(exc)
            raise

    def delete_user(self, *, platform: PlatformName, user_id: str) -> None:
        uid = self._normalize_user_id(platform, user_id)
        protected_uid = PROTECTED_ADMIN_USER_IDS[platform]
        if uid == protected_uid:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete protected admin user for {platform}: {protected_uid}",
            )
        try:
            self._client(platform).delete_user(user_id=uid)
        except Exception as exc:  # noqa: BLE001
            self._map_exception(exc)
            raise


def get_platform_user_admin_service() -> Generator[PlatformUserAdminService, None, None]:
    service = PlatformUserAdminService.build()
    try:
        yield service
    finally:
        service.vocechat.close()
        service.memos.close()
        service.openwebui.close()

