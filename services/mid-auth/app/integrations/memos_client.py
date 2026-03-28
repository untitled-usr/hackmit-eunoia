"""Memos HTTP client: user provisioning, Attachment/Shortcut services, memo CRUD.

Operations that act as a Memos user send ``X-Acting-Uid``; Memos enforces ACL.
The mid-auth posts layer does not duplicate creator checks.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)


class MemosClientError(Exception):
    """Logical or HTTP failure talking to Memos."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        transport: bool = False,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.transport = transport


class MemosClient:
    """base_url is origin only, e.g. http://127.0.0.1:7921 (no /api/v1 suffix)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        acting_uid_header: str,
        admin_acting_uid: str | None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._acting_header = acting_uid_header
        self._admin_acting_uid = admin_acting_uid
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def create_user(self) -> tuple[str, str | None]:
        """POST /api/v1/users — returns (resource name e.g. users/1, username or None)."""
        url = f"{self._base}/api/v1/users"
        try:
            response = self._client.post(url, json={})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"CreateUser failed: {exc.response.status_code} {exc.response.text[:500]}"
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(f"CreateUser request failed: {exc}") from exc

        data: dict[str, Any] = response.json()
        name = data.get("name")
        if not name:
            raise MemosClientError("CreateUser response missing name")
        username = data.get("username")
        return str(name), str(username) if username else None

    def delete_user_best_effort(self, resource_name: str) -> None:
        """resource_name like users/123."""
        if not self._admin_acting_uid:
            log.warning("Memos admin acting uid not set; skip delete for %s", resource_name)
            return
        if not resource_name.startswith("users/"):
            log.warning("Memos unexpected resource name %s; skip delete", resource_name)
            return
        user_id = resource_name.split("/", 1)[1]
        url = f"{self._base}/api/v1/users/{user_id}"
        try:
            response = self._client.delete(
                url,
                headers={self._acting_header: self._admin_acting_uid},
            )
            if response.status_code >= 400:
                log.warning(
                    "Memos delete user %s failed: %s %s",
                    resource_name,
                    response.status_code,
                    response.text[:300],
                )
        except httpx.RequestError as exc:
            log.warning("Memos delete user %s request error: %s", resource_name, exc)

    def _acting_headers(self, acting_uid: str) -> dict[str, str]:
        return {self._acting_header: acting_uid.strip()}

    def _admin_headers(self) -> dict[str, str]:
        if not (self._admin_acting_uid or "").strip():
            raise MemosClientError(
                "Memos admin acting uid is not configured",
                http_status=503,
            )
        return {self._acting_header: self._admin_acting_uid.strip()}

    def _http_exc(
        self, exc: httpx.HTTPStatusError, label: str
    ) -> MemosClientError:
        return MemosClientError(
            f"{label} failed: {exc.response.status_code} {exc.response.text[:500]}",
            http_status=exc.response.status_code,
        )

    # --- InstanceService ---

    def get_instance_setting(
        self,
        setting_suffix: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/instance/settings/{suffix} with ``X-Acting-Uid``."""
        suf = setting_suffix.strip().lstrip("/")
        url = f"{self._base}/api/v1/instance/settings/{quote(suf, safe='')}"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetInstanceSetting") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetInstanceSetting request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_instance_setting(
        self,
        setting_suffix: str,
        *,
        update_mask: str,
        body: dict[str, Any],
        acting_uid: str,
    ) -> dict[str, Any]:
        suf = setting_suffix.strip().lstrip("/")
        url = f"{self._base}/api/v1/instance/settings/{quote(suf, safe='')}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateInstanceSetting") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateInstanceSetting request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_instance_dynamic_setting(
        self,
        setting_key_path: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/instance/settings/* with ``X-Acting-Uid`` (user library BFF)."""
        return self.get_instance_setting(setting_key_path, acting_uid=acting_uid)

    def patch_instance_dynamic_setting(
        self,
        setting_key_path: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """PATCH /api/v1/instance/settings/* as the acting user."""
        return self.update_instance_setting(
            setting_key_path,
            update_mask=update_mask,
            body=body,
            acting_uid=acting_uid,
        )

    # --- UserService (beyond create / delete_user_best_effort) ---

    def get_user_stats(
        self,
        user_ref: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/users/{ref}:getStats"""
        ref = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{ref}:getStats"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetUserStats") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetUserStats request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_user_setting(
        self,
        user_ref: str,
        setting_key: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        s = quote(setting_key.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/settings/{s}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetUserSetting") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetUserSetting request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_user_setting(
        self,
        user_ref: str,
        setting_key: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        s = quote(setting_key.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/settings/{s}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateUserSetting") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateUserSetting request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_user_settings(
        self,
        user_ref: str,
        *,
        acting_uid: str,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/settings"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListUserSettings") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListUserSettings request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_user_webhooks(
        self,
        user_ref: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/webhooks"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListUserWebhooks") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListUserWebhooks request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def create_user_webhook(
        self,
        user_ref: str,
        *,
        acting_uid: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/webhooks"
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "CreateUserWebhook") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateUserWebhook request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_user_webhook(
        self,
        user_ref: str,
        webhook_id: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        w = quote(webhook_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/webhooks/{w}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateUserWebhook") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateUserWebhook request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_user_webhook(
        self,
        user_ref: str,
        webhook_id: str,
        *,
        acting_uid: str,
    ) -> None:
        u = quote(user_ref.strip(), safe="")
        w = quote(webhook_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/webhooks/{w}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "DeleteUserWebhook") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteUserWebhook request failed: {exc}", transport=True
            ) from exc

    def list_user_notifications(
        self,
        user_ref: str,
        *,
        acting_uid: str,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/notifications"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListUserNotifications") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListUserNotifications request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_user_notification(
        self,
        user_ref: str,
        notification_id: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        u = quote(user_ref.strip(), safe="")
        n = quote(notification_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/notifications/{n}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateUserNotification") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateUserNotification request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_user_notification(
        self,
        user_ref: str,
        notification_id: str,
        *,
        acting_uid: str,
    ) -> None:
        u = quote(user_ref.strip(), safe="")
        n = quote(notification_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/notifications/{n}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "DeleteUserNotification") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteUserNotification request failed: {exc}", transport=True
            ) from exc

    # --- MemoService extensions ---

    def update_memo(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """PATCH /api/v1/memos/{uid} — arbitrary fields per ``update_mask``."""
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateMemo") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateMemo request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def set_memo_attachments(
        self, acting_uid: str, memo_uid: str, *, body: dict[str, Any]
    ) -> None:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/attachments"
        try:
            response = self._client.patch(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "SetMemoAttachments") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"SetMemoAttachments request failed: {exc}", transport=True
            ) from exc

    def list_memo_attachments(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/attachments"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListMemoAttachments") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListMemoAttachments request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def set_memo_relations(
        self, acting_uid: str, memo_uid: str, *, body: dict[str, Any]
    ) -> None:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/relations"
        try:
            response = self._client.patch(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "SetMemoRelations") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"SetMemoRelations request failed: {exc}", transport=True
            ) from exc

    def list_memo_relations(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/relations"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListMemoRelations") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListMemoRelations request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def create_memo_comment(
        self, acting_uid: str, memo_uid: str, *, body: dict[str, Any]
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/comments"
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "CreateMemoComment") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateMemoComment request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_memo_comments(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/comments"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        if order_by:
            params["orderBy"] = order_by
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListMemoComments") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListMemoComments request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_memo_reactions(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/reactions"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListMemoReactions") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListMemoReactions request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def upsert_memo_reaction(
        self, acting_uid: str, memo_uid: str, *, body: dict[str, Any]
    ) -> dict[str, Any]:
        uid = self._normalize_memo_uid(memo_uid)
        url = f"{self._base}/api/v1/memos/{quote(uid, safe='')}/reactions"
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpsertMemoReaction") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpsertMemoReaction request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_memo_reaction(
        self, acting_uid: str, memo_uid: str, reaction_id: str
    ) -> None:
        """``reaction_id`` is the last segment of ``memos/{m}/reactions/{r}``."""
        uid = self._normalize_memo_uid(memo_uid)
        rid = quote(reaction_id.strip(), safe="")
        url = (
            f"{self._base}/api/v1/memos/{quote(uid, safe='')}/reactions/{rid}"
        )
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "DeleteMemoReaction") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteMemoReaction request failed: {exc}", transport=True
            ) from exc

    # --- AttachmentService (/api/v1/attachments) ---

    @staticmethod
    def _normalize_attachment_ref(attachment_ref: str) -> str:
        r = attachment_ref.strip()
        if r.startswith("attachments/"):
            return r.split("/", 1)[1]
        return r

    def create_attachment(
        self,
        acting_uid: str,
        *,
        body: dict[str, Any],
        attachment_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/attachments — JSON body is the Attachment message (grpc-gateway)."""
        url = f"{self._base}/api/v1/attachments"
        params: dict[str, Any] = {}
        if attachment_id:
            params["attachmentId"] = attachment_id
        try:
            response = self._client.post(
                url,
                json=body,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "CreateAttachment") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateAttachment request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_attachments(
        self,
        acting_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        filter_expr: str | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/attachments"""
        url = f"{self._base}/api/v1/attachments"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        if order_by:
            params["orderBy"] = order_by
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListAttachments") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListAttachments request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_attachment(
        self,
        attachment_ref: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/attachments/{id} — ``attachment_ref`` may be ``attachments/x`` or ``x``."""
        aid = quote(self._normalize_attachment_ref(attachment_ref), safe="")
        url = f"{self._base}/api/v1/attachments/{aid}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetAttachment") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetAttachment request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_attachment(
        self,
        attachment_ref: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """PATCH /api/v1/attachments/{id} — body is Attachment JSON; path must match ``name``."""
        aid = quote(self._normalize_attachment_ref(attachment_ref), safe="")
        url = f"{self._base}/api/v1/attachments/{aid}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": update_mask},
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateAttachment") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateAttachment request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_attachment(
        self,
        attachment_ref: str,
        *,
        acting_uid: str,
    ) -> None:
        """DELETE /api/v1/attachments/{id}"""
        aid = quote(self._normalize_attachment_ref(attachment_ref), safe="")
        url = f"{self._base}/api/v1/attachments/{aid}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "DeleteAttachment") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteAttachment request failed: {exc}", transport=True
            ) from exc

    # --- ShortcutService (users/{user}/shortcuts) ---

    def list_shortcuts(
        self,
        user_ref: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/users/{user}/shortcuts"""
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/shortcuts"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ListShortcuts") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListShortcuts request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_shortcut(
        self,
        user_ref: str,
        shortcut_id: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        """GET /api/v1/users/{user}/shortcuts/{shortcut}"""
        u = quote(user_ref.strip(), safe="")
        s = quote(shortcut_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/shortcuts/{s}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetShortcut") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetShortcut request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def create_shortcut(
        self,
        user_ref: str,
        *,
        acting_uid: str,
        body: dict[str, Any],
        validate_only: bool | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/users/{user}/shortcuts — body is Shortcut JSON."""
        u = quote(user_ref.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/shortcuts"
        params: dict[str, Any] = {}
        if validate_only is not None:
            # grpc-gateway expects lowercase boolean query strings
            params["validateOnly"] = "true" if validate_only else "false"
        try:
            response = self._client.post(
                url,
                json=body,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "CreateShortcut") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateShortcut request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_shortcut(
        self,
        user_ref: str,
        shortcut_id: str,
        *,
        acting_uid: str,
        body: dict[str, Any],
        update_mask: str | None = None,
    ) -> dict[str, Any]:
        """PATCH /api/v1/users/{user}/shortcuts/{id} — body is Shortcut JSON."""
        u = quote(user_ref.strip(), safe="")
        s = quote(shortcut_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/shortcuts/{s}"
        params: dict[str, Any] = {}
        if update_mask:
            params["updateMask"] = update_mask
        try:
            response = self._client.patch(
                url,
                json=body,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "UpdateShortcut") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateShortcut request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_shortcut(
        self,
        user_ref: str,
        shortcut_id: str,
        *,
        acting_uid: str,
    ) -> None:
        """DELETE /api/v1/users/{user}/shortcuts/{shortcut}"""
        u = quote(user_ref.strip(), safe="")
        s = quote(shortcut_id.strip(), safe="")
        url = f"{self._base}/api/v1/users/{u}/shortcuts/{s}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "DeleteShortcut") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteShortcut request failed: {exc}", transport=True
            ) from exc

    @staticmethod
    def _normalize_memo_uid(memo_uid: str) -> str:
        return memo_uid.strip().removeprefix("memos/")

    def create_memo(
        self,
        acting_uid: str,
        *,
        content: str,
        visibility: str = "PRIVATE",
        location: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/memos — body is Memo JSON (camelCase).

        Platform posts v1 calls this with ``visibility="PRIVATE"`` only; callers
        rely on Memos to attribute the memo to ``acting_uid``.
        """
        url = f"{self._base}/api/v1/memos"
        payload: dict[str, Any] = {"content": content, "visibility": visibility}
        if location is not None:
            payload["location"] = location
        try:
            response = self._client.post(
                url,
                json=payload,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"CreateMemo failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateMemo request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def list_memos(
        self,
        acting_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        filter_expr: str | None = None,
        state: str | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/memos — query uses camelCase (OpenAPI)."""
        url = f"{self._base}/api/v1/memos"
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        if state:
            params["state"] = state
        if order_by:
            params["orderBy"] = order_by
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"ListMemos failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ListMemos request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_memo(self, acting_uid: str, memo_uid: str) -> dict[str, Any]:
        """GET /api/v1/memos/{memo_uid}"""
        uid = memo_uid.strip().removeprefix("memos/")
        url = f"{self._base}/api/v1/memos/{uid}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"GetMemo failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetMemo request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def update_memo_content(
        self, acting_uid: str, memo_uid: str, *, content: str
    ) -> dict[str, Any]:
        """PATCH /api/v1/memos/{memo_uid}?updateMask=content"""
        uid = memo_uid.strip().removeprefix("memos/")
        url = f"{self._base}/api/v1/memos/{uid}"
        try:
            response = self._client.patch(
                url,
                params={"updateMask": "content"},
                json={"content": content},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"UpdateMemo failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"UpdateMemo request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def delete_memo(self, acting_uid: str, memo_uid: str) -> None:
        """DELETE /api/v1/memos/{memo_uid}"""
        uid = memo_uid.strip().removeprefix("memos/")
        url = f"{self._base}/api/v1/memos/{uid}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MemosClientError(
                f"DeleteMemo failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"DeleteMemo request failed: {exc}", transport=True
            ) from exc

    # --- DriftBottleService (/api/v1/drift-bottles*) ---

    @staticmethod
    def _normalize_drift_bottle_ref(drift_bottle_ref: str) -> str:
        ref = drift_bottle_ref.strip()
        if ref.startswith("drift-bottles/"):
            return ref.split("/", 1)[1]
        return ref

    def create_drift_bottle(
        self, acting_uid: str, *, body: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /api/v1/drift-bottles"""
        url = f"{self._base}/api/v1/drift-bottles"
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "CreateDriftBottle") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"CreateDriftBottle request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def get_drift_bottle(
        self, drift_bottle_ref: str, *, acting_uid: str
    ) -> dict[str, Any]:
        """GET /api/v1/drift-bottles/{id}"""
        rid = quote(self._normalize_drift_bottle_ref(drift_bottle_ref), safe="")
        url = f"{self._base}/api/v1/drift-bottles/{rid}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "GetDriftBottle") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"GetDriftBottle request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def reply_drift_bottle(
        self,
        acting_uid: str,
        drift_bottle_ref: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /api/v1/drift-bottles/{id}:reply"""
        rid = quote(self._normalize_drift_bottle_ref(drift_bottle_ref), safe="")
        url = f"{self._base}/api/v1/drift-bottles/{rid}:reply"
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "ReplyDriftBottle") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"ReplyDriftBottle request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def pick_drift_bottle(self, acting_uid: str) -> dict[str, Any]:
        """POST /api/v1/drift-bottles:pick"""
        url = f"{self._base}/api/v1/drift-bottles:pick"
        try:
            response = self._client.post(
                url,
                json={},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "PickDriftBottle") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"PickDriftBottle request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def refresh_my_drift_bottle_candidates(
        self, acting_uid: str
    ) -> dict[str, Any]:
        """POST /api/v1/drift-bottles:refreshMine"""
        url = f"{self._base}/api/v1/drift-bottles:refreshMine"
        try:
            response = self._client.post(
                url,
                json={},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "RefreshMyDriftBottleCandidates") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"RefreshMyDriftBottleCandidates request failed: {exc}",
                transport=True,
            ) from exc
        return response.json()

    def search_drift_bottles(
        self,
        acting_uid: str,
        *,
        tag: str,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/drift-bottles:search"""
        url = f"{self._base}/api/v1/drift-bottles:search"
        params: dict[str, Any] = {"tag": tag}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._http_exc(exc, "SearchDriftBottles") from exc
        except httpx.RequestError as exc:
            raise MemosClientError(
                f"SearchDriftBottles request failed: {exc}", transport=True
            ) from exc
        return response.json()
