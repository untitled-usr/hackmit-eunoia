"""VoceChat HTTP client: register/delete, DM, message edit/like/delete/reply, session logout, user search, social, preferences, push device tokens, groups, favorites."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx

log = logging.getLogger(__name__)


def build_vocechat_user_events_url(
    api_base_url: str,
    *,
    after_mid: int | None = None,
    users_version: int | None = None,
) -> str:
    """Absolute URL for VoceChat ``GET /user/events`` (used by the SSE proxy only)."""
    root = api_base_url.rstrip("/")
    q: list[tuple[str, str]] = []
    if after_mid is not None:
        q.append(("after_mid", str(int(after_mid))))
    if users_version is not None:
        q.append(("users_version", str(int(users_version))))
    path = f"{root}/user/events"
    if not q:
        return path
    return f"{path}?{urlencode(q)}"


class VoceChatClientError(Exception):
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


class VoceChatClient:
    """base_url must include ``/api`` suffix (per OpenAPI servers)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        acting_uid_header: str,
        admin_acting_uid: str | None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._acting_header = acting_uid_header
        self._client = httpx.Client(timeout=timeout_seconds)
        au = (admin_acting_uid or "").strip()
        self._admin_acting_uid: str | None = au if au else None

    def close(self) -> None:
        self._client.close()

    def _acting_headers(self, acting_uid: str) -> dict[str, str]:
        return {self._acting_header: acting_uid.strip()}

    def build_user_events_url(
        self,
        *,
        after_mid: int | None = None,
        users_version: int | None = None,
    ) -> str:
        """URL for VoceChat user event stream (SSE); prefer async proxy, not sync ``httpx.Client``."""
        return build_vocechat_user_events_url(
            self._base,
            after_mid=after_mid,
            users_version=users_version,
        )

    def register(self, name: str, password: str) -> tuple[int, str]:
        """POST /user/register — returns (uid, name)."""
        url = f"{self._base}/user/register"
        body: dict[str, Any] = {
            "password": password,
            "name": name[:32],
            "language": "en-US",
            "gender": 0,
            "device": "unknown",
        }
        try:
            response = self._client.post(url, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"register failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"register request failed: {exc}", transport=True
            ) from exc

        data: dict[str, Any] = response.json()
        uid = data.get("uid")
        if uid is None:
            raise VoceChatClientError("register response missing uid")
        display_name = str(data.get("name", "") or name[:32])
        return int(uid), display_name

    def delete_current_user(self, acting_uid: str) -> None:
        """DELETE /user/delete — remove the VoceChat user bound to the acting token."""
        url = f"{self._base}/user/delete"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete current user failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete current user request failed: {exc}", transport=True
            ) from exc

    def delete_user_best_effort(self, uid: int) -> None:
        """DELETE /admin/user/{uid} — logs and swallows errors (provisioning rollback)."""
        if not self._admin_acting_uid:
            log.warning("VoceChat admin acting uid not set; skip delete for %s", uid)
            return
        url = f"{self._base}/admin/user/{int(uid)}"
        try:
            response = self._client.delete(
                url,
                headers={self._acting_header: self._admin_acting_uid},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "VoceChat delete user %s failed: %s %s",
                uid,
                exc.response.status_code,
                exc.response.text[:300],
            )
        except httpx.RequestError as exc:
            log.warning("VoceChat delete user %s request error: %s", uid, exc)

    def list_contacts(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /user/contacts — raw JSON objects (platform maps to DTOs)."""
        url = f"{self._base}/user/contacts"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list contacts failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list contacts request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_user_devices(self, acting_uid: str) -> list[str]:
        """GET /user/devices — VoceChat device keys (opaque strings)."""
        url = f"{self._base}/user/devices"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list devices failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list devices transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        out: list[str] = []
        for x in data:
            if isinstance(x, str):
                out.append(x)
            elif x is not None:
                out.append(str(x))
        return out

    def delete_user_device(self, acting_uid: str, device: str) -> None:
        """DELETE /user/devices/{device}"""
        enc = quote(str(device), safe="")
        url = f"{self._base}/user/devices/{enc}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete device failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete device transport: {exc}", transport=True
            ) from exc

    def get_dm_history(
        self,
        acting_uid: str,
        peer_uid: int,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """GET /user/{peer_uid}/history"""
        url = f"{self._base}/user/{peer_uid}/history"
        params: dict[str, Any] = {"limit": limit}
        if before_message_id is not None:
            params["before"] = before_message_id
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get history failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get history request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def update_read_index(
        self,
        acting_uid: str,
        *,
        users: list[dict[str, int]] | None = None,
        groups: list[dict[str, int]] | None = None,
    ) -> None:
        """POST /user/read-index — ``users`` items ``{uid, mid}``, ``groups`` items ``{gid, mid}``."""
        url = f"{self._base}/user/read-index"
        body: dict[str, Any] = {
            "users": list(users) if users is not None else [],
            "groups": list(groups) if groups is not None else [],
        }
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"update read index failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"update read index transport: {exc}", transport=True
            ) from exc

    def user_logout(self, acting_uid: str) -> None:
        """POST /user/logout — drop current acting-uid session (same effect as removing the SSE device)."""
        url = f"{self._base}/user/logout"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"user logout failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"user logout request failed: {exc}", transport=True
            ) from exc

    def send_dm_text(self, acting_uid: str, peer_uid: int, text: str) -> int:
        """POST /user/{peer_uid}/send with text/plain body."""
        url = f"{self._base}/user/{peer_uid}/send"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": "text/plain",
        }
        try:
            response = self._client.post(
                url,
                content=text.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"send message failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"send message request failed: {exc}", transport=True
            ) from exc
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "send message: invalid response", http_status=response.status_code
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            "send message: response missing message id", http_status=response.status_code
        )

    def _prepare_file_upload_at(
        self,
        prepare_path: str,
        acting_uid: str,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        op_label: str = "prepare file upload",
    ) -> str:
        """POST ``/{prepare_path}`` — returns ``file_id`` (UUID string)."""
        rel = prepare_path.strip().strip("/")
        url = f"{self._base}/{rel}"
        body: dict[str, Any] = {}
        if content_type is not None:
            body["content_type"] = content_type
        if filename is not None:
            body["filename"] = filename
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"{op_label} failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"{op_label} transport: {exc}", transport=True
            ) from exc
        try:
            file_id = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                f"{op_label}: invalid response",
                http_status=response.status_code,
            ) from exc
        if not isinstance(file_id, str) or not file_id.strip():
            raise VoceChatClientError(
                f"{op_label}: expected non-empty string file_id",
                http_status=response.status_code,
            )
        return file_id.strip()

    def _upload_file_chunk_at(
        self,
        upload_path: str,
        acting_uid: str,
        file_id: str,
        chunk: bytes,
        *,
        chunk_is_last: bool,
        op_label: str = "file upload",
    ) -> dict[str, Any] | None:
        """POST ``/{upload_path}`` (multipart). Returns upload result JSON when ``chunk_is_last``."""
        rel = upload_path.strip().strip("/")
        url = f"{self._base}/{rel}"
        data = {
            "file_id": file_id,
            "chunk_is_last": "true" if chunk_is_last else "false",
        }
        files = {"chunk_data": ("chunk", chunk, "application/octet-stream")}
        try:
            response = self._client.post(
                url,
                data=data,
                files=files,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"{op_label} failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"{op_label} transport: {exc}", transport=True
            ) from exc
        try:
            payload = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                f"{op_label}: invalid response", http_status=response.status_code
            ) from exc
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise VoceChatClientError(
                f"{op_label}: expected object or null",
                http_status=response.status_code,
            )
        return payload

    def prepare_file_upload(
        self,
        acting_uid: str,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        """POST /resource/file/prepare — returns ``file_id`` (UUID string)."""
        return self._prepare_file_upload_at(
            "resource/file/prepare",
            acting_uid,
            content_type=content_type,
            filename=filename,
        )

    def prepare_bot_file_upload(
        self,
        acting_uid: str,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        """POST /bot/file/prepare — same semantics as ``prepare_file_upload`` (bot acting uid)."""
        return self._prepare_file_upload_at(
            "bot/file/prepare",
            acting_uid,
            content_type=content_type,
            filename=filename,
            op_label="prepare bot file upload",
        )

    def upload_file_chunk(
        self,
        acting_uid: str,
        file_id: str,
        chunk: bytes,
        *,
        chunk_is_last: bool,
    ) -> dict[str, Any] | None:
        """POST /resource/file/upload (multipart). Returns upload result JSON when ``chunk_is_last``."""
        return self._upload_file_chunk_at(
            "resource/file/upload",
            acting_uid,
            file_id,
            chunk,
            chunk_is_last=chunk_is_last,
        )

    def upload_bot_file_chunk(
        self,
        acting_uid: str,
        file_id: str,
        chunk: bytes,
        *,
        chunk_is_last: bool,
    ) -> dict[str, Any] | None:
        """POST /bot/file/upload — same as ``upload_file_chunk`` (bot acting uid)."""
        return self._upload_file_chunk_at(
            "bot/file/upload",
            acting_uid,
            file_id,
            chunk,
            chunk_is_last=chunk_is_last,
            op_label="bot file upload",
        )

    def upload_file_complete(
        self,
        acting_uid: str,
        data: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Prepare, upload in one chunk with ``chunk_is_last=true``, return VoceChat ``UploadFileResponse``."""
        file_id = self.prepare_file_upload(
            acting_uid, content_type=content_type, filename=filename
        )
        result = self.upload_file_chunk(
            acting_uid, file_id, data, chunk_is_last=True
        )
        if not result:
            raise VoceChatClientError(
                "file upload: missing response on final chunk",
                http_status=None,
            )
        path = result.get("path")
        if not isinstance(path, str) or not path.strip():
            raise VoceChatClientError(
                "file upload: response missing path",
                http_status=None,
            )
        return result

    def send_dm_file(self, acting_uid: str, peer_uid: int, storage_path: str) -> int:
        """POST /user/{peer_uid}/send with ``Content-Type: vocechat/file`` and ``{{path}}`` JSON."""
        url = f"{self._base}/user/{peer_uid}/send"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": "vocechat/file",
        }
        try:
            response = self._client.post(
                url,
                json={"path": storage_path.strip()},
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"send file message failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"send file message transport: {exc}", transport=True
            ) from exc
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "send file message: invalid response", http_status=response.status_code
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            "send file message: response missing message id",
            http_status=response.status_code,
        )

    def stream_resource_file_get(
        self,
        acting_uid: str,
        *,
        file_path: str,
        thumbnail: bool = False,
        download: bool = False,
        forward_headers: dict[str, str] | None = None,
    ):
        """Context manager: ``GET /resource/file`` (streaming body for 2xx/206)."""
        url = f"{self._base}/resource/file"
        params: dict[str, Any] = {
            "file_path": file_path,
            "thumbnail": thumbnail,
            "download": download,
        }
        headers = {**self._acting_headers(acting_uid)}
        if forward_headers:
            headers.update(forward_headers)
        return self._client.stream(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )

    def stream_resource_group_avatar_get(
        self,
        acting_uid: str,
        *,
        gid: int,
        forward_headers: dict[str, str] | None = None,
    ):
        """Context manager: ``GET /resource/group_avatar`` (``gid`` query)."""
        url = f"{self._base}/resource/group_avatar"
        params: dict[str, Any] = {"gid": int(gid)}
        headers = {**self._acting_headers(acting_uid)}
        if forward_headers:
            headers.update(forward_headers)
        return self._client.stream(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )

    def stream_resource_organization_logo_get(
        self,
        acting_uid: str,
        *,
        cache_buster: int | None = None,
        forward_headers: dict[str, str] | None = None,
    ):
        """Context manager: ``GET /resource/organization/logo`` (optional ``t`` cache buster)."""
        url = f"{self._base}/resource/organization/logo"
        params: dict[str, Any] = {}
        if cache_buster is not None:
            params["t"] = int(cache_buster)
        headers = {**self._acting_headers(acting_uid)}
        if forward_headers:
            headers.update(forward_headers)
        return self._client.stream(
            "GET",
            url,
            params=params if params else None,
            headers=headers,
            timeout=self._timeout,
        )

    def delete_resource_file(self, acting_uid: str, *, file_path: str) -> None:
        """``DELETE /resource/file`` with ``file_path`` query (VoceChat may return 405 if unsupported)."""
        url = f"{self._base}/resource/file"
        try:
            response = self._client.delete(
                url,
                params={"file_path": file_path},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete resource file failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete resource file transport: {exc}", transport=True
            ) from exc

    def create_message_archive(
        self, acting_uid: str, mid_list: list[int]
    ) -> str:
        """POST /resource/archive — returns relative storage path string."""
        url = f"{self._base}/resource/archive"
        try:
            response = self._client.post(
                url,
                json={"mid_list": [int(x) for x in mid_list]},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"create archive failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"create archive transport: {exc}", transport=True
            ) from exc
        try:
            raw = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "create archive: invalid response",
                http_status=response.status_code,
            ) from exc
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        raise VoceChatClientError(
            "create archive: expected JSON string path",
            http_status=response.status_code,
        )

    def get_archive_info(self, acting_uid: str, *, file_path: str) -> dict[str, Any]:
        """GET /resource/archive?file_path= — ``Archive`` JSON (acting header sent; VC may ignore)."""
        url = f"{self._base}/resource/archive"
        try:
            response = self._client.get(
                url,
                params={"file_path": file_path},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get archive failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get archive transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "get archive: expected JSON object",
                http_status=response.status_code,
            )
        return data

    def stream_resource_archive_attachment_get(
        self,
        acting_uid: str,
        *,
        file_path: str,
        attachment_id: int,
        download: bool = False,
    ):
        """Context manager: ``GET /resource/archive/attachment``."""
        url = f"{self._base}/resource/archive/attachment"
        params: dict[str, Any] = {
            "file_path": file_path,
            "attachment_id": int(attachment_id),
            "download": download,
        }
        return self._client.stream(
            "GET",
            url,
            params=params,
            headers=self._acting_headers(acting_uid),
            timeout=self._timeout,
        )

    def get_open_graphic_parse(
        self,
        *,
        target_url: str,
        accept_language: str | None = None,
    ) -> dict[str, Any]:
        """GET /resource/open_graphic_parse — no acting token on VoceChat; optional ``Accept-Language``."""
        url = f"{self._base}/resource/open_graphic_parse"
        headers: dict[str, str] = {}
        if accept_language:
            headers["Accept-Language"] = accept_language
        try:
            response = self._client.get(
                url,
                params={"url": target_url},
                headers=headers or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"open graphic parse failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"open graphic parse transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return data

    @staticmethod
    def _mid_from_json_response(response: httpx.Response, *, context: str) -> int:
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                f"{context}: invalid response", http_status=response.status_code
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            f"{context}: response missing message id",
            http_status=response.status_code,
        )

    def message_edit(
        self,
        acting_uid: str,
        mid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        """PUT /message/{mid}/edit — same body/content types as OpenAPI (text, markdown, file, archive)."""
        url = f"{self._base}/message/{int(mid)}/edit"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": content_type,
        }
        if x_properties:
            headers["X-Properties"] = x_properties
        try:
            response = self._client.put(
                url, content=raw_body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"message edit failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"message edit transport: {exc}", transport=True
            ) from exc
        return self._mid_from_json_response(response, context="message edit")

    def message_like(self, acting_uid: str, mid: int, *, action: str) -> int:
        """PUT /message/{mid}/like — JSON ``{{"action": ...}}``."""
        url = f"{self._base}/message/{int(mid)}/like"
        try:
            response = self._client.put(
                url,
                json={"action": str(action)},
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"message like failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"message like transport: {exc}", transport=True
            ) from exc
        return self._mid_from_json_response(response, context="message like")

    def message_delete(self, acting_uid: str, mid: int) -> int:
        """DELETE /message/{mid}"""
        url = f"{self._base}/message/{int(mid)}"
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"message delete failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"message delete transport: {exc}", transport=True
            ) from exc
        return self._mid_from_json_response(response, context="message delete")

    def message_reply(
        self,
        acting_uid: str,
        mid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        """POST /message/{mid}/reply"""
        url = f"{self._base}/message/{int(mid)}/reply"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": content_type,
        }
        if x_properties:
            headers["X-Properties"] = x_properties
        try:
            response = self._client.post(
                url, content=raw_body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"message reply failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"message reply transport: {exc}", transport=True
            ) from exc
        return self._mid_from_json_response(response, context="message reply")

    # --- Social (friend requests, friends, blacklist) ---

    def create_friend_request(
        self, acting_uid: str, receiver_uid: int, message: str = ""
    ) -> int:
        """POST /user/friend_requests — returns new request id (int64)."""
        url = f"{self._base}/user/friend_requests"
        body: dict[str, Any] = {"receiver_uid": receiver_uid, "message": message or ""}
        try:
            response = self._client.post(
                url, json=body, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"create friend request failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"create friend request transport: {exc}", transport=True
            ) from exc
        try:
            rid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "create friend request: invalid response",
                http_status=response.status_code,
            ) from exc
        if isinstance(rid, int):
            return rid
        raise VoceChatClientError(
            "create friend request: expected integer id",
            http_status=response.status_code,
        )

    def list_friend_requests_incoming(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /user/friend_requests/incoming"""
        url = f"{self._base}/user/friend_requests/incoming"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list incoming friend requests failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list incoming friend requests transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_friend_requests_outgoing(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /user/friend_requests/outgoing"""
        url = f"{self._base}/user/friend_requests/outgoing"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list outgoing friend requests failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list outgoing friend requests transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_friend_requests_records(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /user/friend_requests/records"""
        url = f"{self._base}/user/friend_requests/records"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list friend request records failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list friend request records transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def accept_friend_request(self, acting_uid: str, request_id: int) -> None:
        url = f"{self._base}/user/friend_requests/{int(request_id)}/accept"
        self._post_empty_ok(url, acting_uid, "accept friend request")

    def reject_friend_request(self, acting_uid: str, request_id: int) -> None:
        url = f"{self._base}/user/friend_requests/{int(request_id)}/reject"
        self._post_empty_ok(url, acting_uid, "reject friend request")

    def cancel_friend_request(self, acting_uid: str, request_id: int) -> None:
        url = f"{self._base}/user/friend_requests/{int(request_id)}/cancel"
        self._post_empty_ok(url, acting_uid, "cancel friend request")

    def delete_friend_request_record(self, acting_uid: str, request_id: int) -> None:
        """DELETE /user/friend_requests/{id} — drop a record when downstream allows."""
        url = f"{self._base}/user/friend_requests/{int(request_id)}"
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete friend request record failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete friend request record transport: {exc}", transport=True
            ) from exc

    def update_contact_status(
        self, acting_uid: str, target_uid: int, action: str
    ) -> None:
        """POST /user/update_contact_status — legacy add/remove/block/unblock."""
        url = f"{self._base}/user/update_contact_status"
        body: dict[str, Any] = {
            "target_uid": int(target_uid),
            "action": action,
        }
        self._post_empty_ok(
            url, acting_uid, "update contact status", json_body=body
        )

    def delete_friend(self, acting_uid: str, peer_uid: int) -> None:
        """DELETE /user/friends/{uid}"""
        url = f"{self._base}/user/friends/{int(peer_uid)}"
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete friend failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete friend transport: {exc}", transport=True
            ) from exc

    def list_blacklist(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /user/blacklist"""
        url = f"{self._base}/user/blacklist"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list blacklist failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list blacklist transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def add_blacklist(self, acting_uid: str, target_uid: int) -> None:
        """POST /user/blacklist/{uid}"""
        url = f"{self._base}/user/blacklist/{int(target_uid)}"
        self._post_empty_ok(url, acting_uid, "add blacklist", json_body=None)

    def remove_blacklist(self, acting_uid: str, target_uid: int) -> None:
        """DELETE /user/blacklist/{uid}"""
        url = f"{self._base}/user/blacklist/{int(target_uid)}"
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"remove blacklist failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"remove blacklist transport: {exc}", transport=True
            ) from exc

    def put_contact_remark(
        self, acting_uid: str, *, target_uid: int, remark: str
    ) -> None:
        """PUT /user/contact_remark — ``ContactRemarkRequest`` JSON (server may no-op)."""
        url = f"{self._base}/user/contact_remark"
        body: dict[str, Any] = {
            "target_uid": int(target_uid),
            "remark": remark,
        }
        self._put_json_ok(url, acting_uid, "contact remark", body)

    def update_mute(self, acting_uid: str, body: dict[str, Any]) -> None:
        """POST /user/mute — ``MuteRequest`` JSON (add/remove users and groups)."""
        url = f"{self._base}/user/mute"
        self._post_empty_ok(url, acting_uid, "update mute", json_body=body)

    def update_burn_after_reading(
        self, acting_uid: str, body: dict[str, Any]
    ) -> None:
        """POST /user/burn-after-reading — ``users`` / ``groups`` with uid/gid + expires_in."""
        url = f"{self._base}/user/burn-after-reading"
        self._post_empty_ok(
            url, acting_uid, "update burn after reading", json_body=body
        )

    def update_fcm_token(
        self, acting_uid: str, *, device_id: str, token: str
    ) -> None:
        """PUT /user/update_fcm_token?device=… — body is FCM token as text/plain."""
        url = f"{self._base}/user/update_fcm_token"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": "text/plain; charset=utf-8",
        }
        try:
            response = self._client.put(
                url,
                params={"device": device_id},
                content=token.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"update fcm token failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"update fcm token transport: {exc}", transport=True
            ) from exc

    def pin_chat(
        self,
        acting_uid: str,
        *,
        dm_peer_uid: int | None = None,
        group_gid: int | None = None,
    ) -> None:
        """POST /user/pin_chat — body matches vocechat-web (``target``: uid or gid)."""
        if (dm_peer_uid is None) == (group_gid is None):
            raise VoceChatClientError(
                "pin_chat: exactly one of dm_peer_uid or group_gid is required"
            )
        if dm_peer_uid is not None:
            body: dict[str, Any] = {"target": {"uid": int(dm_peer_uid)}}
        else:
            body = {"target": {"gid": int(group_gid)}}
        url = f"{self._base}/user/pin_chat"
        self._post_empty_ok(url, acting_uid, "pin chat", json_body=body)

    def unpin_chat(
        self,
        acting_uid: str,
        *,
        dm_peer_uid: int | None = None,
        group_gid: int | None = None,
    ) -> None:
        """POST /user/unpin_chat — same ``target`` shape as ``pin_chat``."""
        if (dm_peer_uid is None) == (group_gid is None):
            raise VoceChatClientError(
                "unpin_chat: exactly one of dm_peer_uid or group_gid is required"
            )
        if dm_peer_uid is not None:
            body: dict[str, Any] = {"target": {"uid": int(dm_peer_uid)}}
        else:
            body = {"target": {"gid": int(group_gid)}}
        url = f"{self._base}/user/unpin_chat"
        self._post_empty_ok(url, acting_uid, "unpin chat", json_body=body)

    def _post_empty_ok(
        self,
        url: str,
        acting_uid: str,
        label: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json=json_body if json_body is not None else {},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"{label} failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"{label} transport: {exc}", transport=True
            ) from exc

    def _put_empty_body_ok(self, url: str, acting_uid: str, label: str) -> None:
        try:
            response = self._client.put(
                url,
                headers=self._acting_headers(acting_uid),
                json={},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"{label} failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"{label} transport: {exc}", transport=True
            ) from exc

    def _put_json_ok(
        self,
        url: str,
        acting_uid: str,
        label: str,
        json_body: dict[str, Any],
    ) -> None:
        try:
            response = self._client.put(
                url,
                headers=self._acting_headers(acting_uid),
                json=json_body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"{label} failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"{label} transport: {exc}", transport=True
            ) from exc

    # --- Groups ---

    def list_groups(
        self, acting_uid: str, *, public_only: bool | None = None
    ) -> list[dict[str, Any]]:
        """GET /group"""
        url = f"{self._base}/group"
        params: dict[str, Any] = {}
        if public_only is not None:
            params["public_only"] = public_only
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list groups failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list groups transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def bot_list_groups(
        self, acting_uid: str, *, public_only: bool | None = None
    ) -> list[dict[str, Any]]:
        """GET /bot — groups related to the acting user (VoceChat bot API)."""
        url = f"{self._base}/bot"
        params: dict[str, Any] = {}
        if public_only is not None:
            params["public_only"] = public_only
        try:
            response = self._client.get(
                url,
                params=params or None,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"bot list groups failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"bot list groups transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def bot_get_user(self, acting_uid: str, peer_uid: int) -> dict[str, Any]:
        """GET /bot/user/{uid} — VoceChat ``UserInfo`` (bot acting token)."""
        url = f"{self._base}/bot/user/{int(peer_uid)}"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"bot get user failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"bot get user transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "bot get user: invalid response", http_status=response.status_code
            )
        return data

    def bot_get_group(self, acting_uid: str, gid: int) -> dict[str, Any]:
        """GET /bot/group/{gid} — VoceChat ``Group`` (bot acting token)."""
        url = f"{self._base}/bot/group/{int(gid)}"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"bot get group failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"bot get group transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "bot get group: invalid response", http_status=response.status_code
            )
        return data

    def create_group(self, acting_uid: str, body: dict[str, Any]) -> tuple[int, int]:
        """POST /group — returns (gid, created_at)."""
        url = f"{self._base}/group"
        try:
            response = self._client.post(
                url, json=body, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"create group failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"create group transport: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "create group: invalid response", http_status=response.status_code
            ) from exc
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "create group: expected object", http_status=response.status_code
            )
        gid = data.get("gid")
        created = data.get("created_at")
        if gid is None or created is None:
            raise VoceChatClientError(
                "create group: missing gid or created_at",
                http_status=response.status_code,
            )
        return int(gid), int(created)

    def get_group(self, acting_uid: str, gid: int) -> dict[str, Any]:
        """GET /group/{gid}"""
        url = f"{self._base}/group/{int(gid)}"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get group failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get group transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "get group: invalid response", http_status=response.status_code
            )
        return data

    def get_group_agora_token(self, acting_uid: str, gid: int) -> dict[str, Any]:
        """GET /group/{gid}/agora_token — RTC token payload for group channel."""
        url = f"{self._base}/group/{int(gid)}/agora_token"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get group agora token failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get group agora token transport: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "get group agora token: invalid response",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise VoceChatClientError(
                "get group agora token: expected object",
                http_status=response.status_code,
            )
        return data

    def delete_group(self, acting_uid: str, gid: int) -> None:
        """DELETE /group/{gid}"""
        url = f"{self._base}/group/{int(gid)}"
        try:
            response = self._client.delete(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete group failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete group transport: {exc}", transport=True
            ) from exc

    def update_group(
        self, acting_uid: str, gid: int, body: dict[str, Any]
    ) -> None:
        """PUT /group/{gid} — ``UpdateGroupRequest`` JSON."""
        url = f"{self._base}/group/{int(gid)}"
        self._put_json_ok(url, acting_uid, "update group", body)

    def group_add_members(
        self, acting_uid: str, gid: int, member_uids: list[int]
    ) -> None:
        url = f"{self._base}/group/{int(gid)}/members/add"
        self._post_empty_ok(
            url, acting_uid, "group add members", json_body=member_uids
        )

    def group_remove_members(
        self, acting_uid: str, gid: int, member_uids: list[int]
    ) -> None:
        url = f"{self._base}/group/{int(gid)}/members/remove"
        self._post_empty_ok(
            url, acting_uid, "group remove members", json_body=member_uids
        )

    def group_change_type(
        self,
        acting_uid: str,
        gid: int,
        *,
        is_public: bool,
        members: list[int],
    ) -> None:
        """POST /group/{gid}/change_type — ``is_public`` + ``members`` (uids)."""
        url = f"{self._base}/group/{int(gid)}/change_type"
        body: dict[str, Any] = {
            "is_public": bool(is_public),
            "members": [int(x) for x in members],
        }
        self._post_empty_ok(url, acting_uid, "group change type", json_body=body)

    def leave_group(self, acting_uid: str, gid: int) -> None:
        """GET /group/{gid}/leave — current user leaves the group."""
        url = f"{self._base}/group/{int(gid)}/leave"
        try:
            response = self._client.get(
                url, headers=self._acting_headers(acting_uid)
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"group leave failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"group leave transport: {exc}", transport=True
            ) from exc

    def send_group_payload(
        self,
        acting_uid: str,
        gid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        """POST /group/{gid}/send — body and Content-Type match VoceChat OpenAPI."""
        url = f"{self._base}/group/{int(gid)}/send"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": content_type,
        }
        if x_properties:
            headers["X-Properties"] = x_properties
        try:
            response = self._client.post(
                url, content=raw_body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"group send failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"group send transport: {exc}", transport=True
            ) from exc
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "group send: invalid response", http_status=response.status_code
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            "group send: response missing message id",
            http_status=response.status_code,
        )

    def upload_group_avatar(
        self, acting_uid: str, gid: int, image_bytes: bytes
    ) -> None:
        """POST ``/group/{gid}/avatar`` with ``image/png`` body (VoceChat ``UploadAvatarRequest``)."""
        url = f"{self._base}/group/{int(gid)}/avatar"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": "image/png",
        }
        try:
            response = self._client.post(
                url, content=image_bytes, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"group avatar upload failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"group avatar upload transport: {exc}", transport=True
            ) from exc

    def send_group_text(self, acting_uid: str, gid: int, text: str) -> int:
        """POST /group/{gid}/send — text/plain body (VoceChat default)."""
        return self.send_group_payload(
            acting_uid,
            gid,
            raw_body=text.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
        )

    def bot_send_to_user_payload(
        self,
        acting_uid: str,
        peer_uid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        """POST /bot/send_to_user/{uid} — body and Content-Type match VoceChat Bot OpenAPI."""
        url = f"{self._base}/bot/send_to_user/{int(peer_uid)}"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": content_type,
        }
        if x_properties:
            headers["X-Properties"] = x_properties
        try:
            response = self._client.post(
                url, content=raw_body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"bot send_to_user failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"bot send_to_user transport: {exc}", transport=True
            ) from exc
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "bot send_to_user: invalid response",
                http_status=response.status_code,
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            "bot send_to_user: response missing message id",
            http_status=response.status_code,
        )

    def bot_send_to_group_payload(
        self,
        acting_uid: str,
        gid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        """POST /bot/send_to_group/{gid} — body and Content-Type match VoceChat Bot OpenAPI."""
        url = f"{self._base}/bot/send_to_group/{int(gid)}"
        headers = {
            **self._acting_headers(acting_uid),
            "Content-Type": content_type,
        }
        if x_properties:
            headers["X-Properties"] = x_properties
        try:
            response = self._client.post(
                url, content=raw_body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"bot send_to_group failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"bot send_to_group transport: {exc}", transport=True
            ) from exc
        try:
            mid = response.json()
        except Exception as exc:
            raise VoceChatClientError(
                "bot send_to_group: invalid response",
                http_status=response.status_code,
            ) from exc
        if isinstance(mid, int):
            return mid
        if isinstance(mid, dict) and "mid" in mid:
            return int(mid["mid"])
        raise VoceChatClientError(
            "bot send_to_group: response missing message id",
            http_status=response.status_code,
        )

    def group_pin_message(self, acting_uid: str, gid: int, mid: int) -> None:
        """POST /group/{gid}/pin — ``PinMessageRequest`` JSON."""
        url = f"{self._base}/group/{int(gid)}/pin"
        self._post_empty_ok(
            url, acting_uid, "group pin message", json_body={"mid": int(mid)}
        )

    def group_unpin_message(self, acting_uid: str, gid: int, mid: int) -> None:
        """POST /group/{gid}/unpin — ``UnpinMessageRequest`` JSON."""
        url = f"{self._base}/group/{int(gid)}/unpin"
        self._post_empty_ok(
            url, acting_uid, "group unpin message", json_body={"mid": int(mid)}
        )

    def get_group_history(
        self,
        acting_uid: str,
        gid: int,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """GET /group/{gid}/history"""
        url = f"{self._base}/group/{int(gid)}/history"
        params: dict[str, Any] = {"limit": limit}
        if before_message_id is not None:
            params["before"] = before_message_id
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"group history failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"group history transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_favorite_archives(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /favorite — list ``FavoriteArchive`` JSON objects."""
        url = f"{self._base}/favorite"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"list favorites failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"list favorites transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def create_favorite_archive(
        self, acting_uid: str, mid_list: list[int]
    ) -> dict[str, Any]:
        """POST /favorite — ``CreateFavoriteRequest``; returns ``FavoriteArchive`` JSON."""
        url = f"{self._base}/favorite"
        body = {"mid_list": [int(x) for x in mid_list]}
        try:
            response = self._client.post(
                url,
                json=body,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"create favorite failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"create favorite transport: {exc}", transport=True
            ) from exc
        out = response.json()
        if not isinstance(out, dict):
            raise VoceChatClientError(
                "create favorite: response is not an object",
                http_status=response.status_code,
            )
        return out

    def delete_favorite_archive(self, acting_uid: str, favorite_id: str) -> None:
        """DELETE /favorite/{id}"""
        enc = quote(str(favorite_id), safe="")
        url = f"{self._base}/favorite/{enc}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"delete favorite failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"delete favorite transport: {exc}", transport=True
            ) from exc

    def get_favorite_archive_info(
        self, acting_uid: str, favorite_id: str
    ) -> dict[str, Any]:
        """GET /favorite/{id} — ``Archive`` JSON."""
        enc = quote(str(favorite_id), safe="")
        url = f"{self._base}/favorite/{enc}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get favorite archive failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get favorite archive transport: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return data

    def get_favorite_attachment_bytes(
        self,
        acting_uid: str,
        owner_uid: int,
        favorite_id: str,
        attachment_id: int,
        *,
        download: bool = False,
    ) -> tuple[bytes, str | None, str | None]:
        """GET /favorite/attachment/{uid}/{id}/{attachment_id} — binary body + headers."""
        enc = quote(str(favorite_id), safe="")
        url = (
            f"{self._base}/favorite/attachment/"
            f"{int(owner_uid)}/{enc}/{int(attachment_id)}"
        )
        params: dict[str, Any] | None = None
        if download:
            params = {"download": True}
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoceChatClientError(
                f"get favorite attachment failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise VoceChatClientError(
                f"get favorite attachment transport: {exc}", transport=True
            ) from exc
        ct = response.headers.get("content-type")
        cd = response.headers.get("content-disposition")
        return response.content or b"", ct, cd


VoceChatClient.get_group_avatar_resource = VoceChatClient.stream_resource_group_avatar_get
VoceChatClient.get_organization_logo_resource = (
    VoceChatClient.stream_resource_organization_logo_get
)
VoceChatClient.get_favorite_attachment = VoceChatClient.get_favorite_attachment_bytes
VoceChatClient.update_group_avatar = VoceChatClient.upload_group_avatar
