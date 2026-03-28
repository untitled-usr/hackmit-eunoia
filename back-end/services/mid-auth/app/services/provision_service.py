"""Orchestrate OpenWebUI, VoceChat, Memos user provisioning (register flow)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.settings import get_settings
from app.integrations.memos_client import MemosClient, MemosClientError
from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.integrations.vocechat_client import VoceChatClient, VoceChatClientError

log = logging.getLogger(__name__)


class ProvisionError(Exception):
    """Provisioning failed; external cleanup was attempted."""

    pass


@dataclass(frozen=True)
class ProvisionResult:
    openwebui_id: str
    openwebui_username: str | None
    vocechat_uid: str
    vocechat_username: str | None
    memos_resource_name: str
    memos_username: str | None


class ProvisionService:
    """Serial create: OpenWebUI -> VoceChat -> Memos. Roll back externals on failure."""

    def provision_user(
        self,
        *,
        display_name: str,
        username: str,
        password: str,
    ) -> ProvisionResult:
        settings = get_settings()

        if settings.provision_use_stub:
            return ProvisionResult(
                openwebui_id="stub-openwebui",
                openwebui_username="stub",
                vocechat_uid="1",
                vocechat_username=username[:32],
                memos_resource_name="users/1",
                memos_username=None,
            )

        if not settings.open_webui_base_url:
            raise ProvisionError("MID_AUTH_OPEN_WEBUI_BASE_URL is not set")
        if not settings.vocechat_base_url:
            raise ProvisionError("MID_AUTH_VOCECHAT_BASE_URL is not set")
        if not settings.memos_base_url:
            raise ProvisionError("MID_AUTH_MEMOS_BASE_URL is not set")

        timeout = float(settings.provision_http_timeout_seconds)
        header = settings.downstream_acting_uid_header

        ow_client = OpenWebUIClient(
            settings.open_webui_base_url,
            timeout,
            header,
            settings.open_webui_admin_acting_uid,
        )
        vc_client = VoceChatClient(
            settings.vocechat_base_url,
            timeout,
            header,
            settings.vocechat_admin_acting_uid,
        )
        mm_client = MemosClient(
            settings.memos_base_url,
            timeout,
            header,
            settings.memos_admin_acting_uid,
        )

        ow_id: str | None = None
        vc_uid: int | None = None
        mm_name: str | None = None

        try:
            ow_id, ow_name = ow_client.register_public()
            vc_name_source = display_name.strip() if display_name else username
            vc_uid_int, vc_name = vc_client.register(
                name=vc_name_source[:32],
                password=password,
            )
            vc_uid = vc_uid_int
            mm_name, mm_username = mm_client.create_user()

            return ProvisionResult(
                openwebui_id=ow_id,
                openwebui_username=ow_name or None,
                vocechat_uid=str(vc_uid_int),
                vocechat_username=vc_name or None,
                memos_resource_name=mm_name,
                memos_username=mm_username,
            )
        except (
            OpenWebUIClientError,
            VoceChatClientError,
            MemosClientError,
        ) as exc:
            log.warning("Provisioning failed: %s", exc)
            self._cleanup(
                ow_client,
                vc_client,
                mm_client,
                ow_id=ow_id,
                vc_uid=vc_uid,
                memos_name=mm_name,
            )
            raise ProvisionError(str(exc)) from exc
        finally:
            ow_client.close()
            vc_client.close()
            mm_client.close()

    @staticmethod
    def _cleanup(
        ow: OpenWebUIClient,
        vc: VoceChatClient,
        mm: MemosClient,
        *,
        ow_id: str | None,
        vc_uid: int | None,
        memos_name: str | None,
    ) -> None:
        if memos_name:
            mm.delete_user_best_effort(memos_name)
        if vc_uid is not None:
            vc.delete_user_best_effort(vc_uid)
        if ow_id:
            ow.delete_user_best_effort(ow_id)
