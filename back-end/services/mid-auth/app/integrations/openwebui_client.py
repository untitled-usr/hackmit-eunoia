"""Open WebUI HTTP client: register/delete, models, chats, completions, tools, memories, etc."""

from __future__ import annotations

import contextlib
import logging
import sys
from typing import Any
from urllib.parse import quote

import httpx

from app.core.proxy_safety import filter_allowlisted_proxy_response_headers

log = logging.getLogger(__name__)


def filter_openwebui_proxy_response_headers(headers: httpx.Headers) -> dict[str, str]:
    """Return only allowlisted, client-safe headers (no cookies, Location, hop-by-hop)."""
    return filter_allowlisted_proxy_response_headers(headers)


class OpenWebUIProxyStream:
    """Holds an open httpx stream response; iterate :meth:`iter_bytes` once, then the context closes."""

    def __init__(self, stream_cm: Any, response: httpx.Response) -> None:
        self._stream_cm = stream_cm
        self.response = response

    def iter_bytes(self) -> Any:
        try:
            yield from self.response.iter_bytes()
        finally:
            self._stream_cm.__exit__(None, None, None)


class OpenWebUIClientError(Exception):
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


class OpenWebUIClient:
    """``base_url`` is origin only (e.g. http://127.0.0.1:8080), without ``/api/v1``."""

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

    def _acting_headers(self, acting_uid: str) -> dict[str, str]:
        return {self._acting_header: acting_uid.strip()}

    def register_public(self) -> tuple[str, str]:
        """POST /api/v1/auths/register — returns (user_id, display_name)."""
        url = f"{self._base}/api/v1/auths/register"
        try:
            response = self._client.post(
                url,
                json={"profile_image_url": "/user.png"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"register failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"register request failed: {exc}", transport=True
            ) from exc

        data: dict[str, Any] = response.json()
        user_id = data.get("id")
        if not user_id:
            raise OpenWebUIClientError("register response missing id")
        name = str(data.get("name", "") or "")
        return str(user_id), name

    def delete_user_best_effort(self, user_id: str) -> None:
        if not self._admin_acting_uid:
            log.warning("OpenWebUI admin acting uid not set; skip delete for %s", user_id)
            return
        url = f"{self._base}/api/v1/users/{user_id}"
        try:
            response = self._client.delete(
                url,
                headers={self._acting_header: self._admin_acting_uid},
            )
            if response.status_code >= 400:
                log.warning(
                    "OpenWebUI delete user %s failed: %s %s",
                    user_id,
                    response.status_code,
                    response.text[:300],
                )
        except httpx.RequestError as exc:
            log.warning("OpenWebUI delete user %s request error: %s", user_id, exc)

    def list_chats(
        self,
        acting_uid: str,
        *,
        page: int | None = None,
        include_pinned: bool | None = None,
        include_folders: bool | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/"
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if include_pinned is not None:
            params["include_pinned"] = include_pinned
        if include_folders is not None:
            params["include_folders"] = include_folders
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_chat(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/{chat_id}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get chat: invalid JSON object")
        return data

    def create_chat(self, acting_uid: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/new"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"chat": chat},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"create chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"create chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("create chat: invalid response")
        return data

    def update_chat(self, acting_uid: str, chat_id: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/{chat_id}"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"chat": chat},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("update chat: invalid response")
        return data

    def delete_chat(self, acting_uid: str, chat_id: str) -> bool:
        """DELETE /api/v1/chats/{chat_id} — returns OW JSON boolean."""
        url = f"{self._base}/api/v1/chats/{chat_id}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete chat request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "delete chat: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("delete chat: expected boolean JSON")

    def chat_completion(self, acting_uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/chat/completions — non-stream JSON body; returns parsed JSON dict."""
        url = f"{self._base}/api/v1/chat/completions"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"chat completion failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"chat completion request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "chat completion: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise OpenWebUIClientError("chat completion: expected JSON object")
        return data

    def _params_optional(
        self,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> dict[str, str]:
        params: dict[str, str] = {}
        if page is not None:
            params["page"] = str(page)
        if query is not None and query != "":
            params["query"] = query
        if order_by is not None and order_by != "":
            params["order_by"] = order_by
        if direction is not None and direction != "":
            params["direction"] = direction
        return params

    def search_chats(
        self,
        acting_uid: str,
        *,
        text: str,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET /api/v1/chats/search — ``text`` is Open WebUI search syntax (incl. ``tag:`` …)."""
        url = f"{self._base}/api/v1/chats/search"
        params: dict[str, str] = {"text": text}
        if page is not None:
            params["page"] = str(page)
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"search chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"search chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_pinned_chats(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/pinned"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list pinned chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list pinned chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_archived_chats(
        self,
        acting_uid: str,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/archived"
        params = self._params_optional(
            page=page, query=query, order_by=order_by, direction=direction
        )
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list archived chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list archived chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_shared_chats(
        self,
        acting_uid: str,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/shared"
        params = self._params_optional(
            page=page, query=query, order_by=order_by, direction=direction
        )
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list shared chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list shared chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_shared_chat_by_share_id(
        self, acting_uid: str, share_id: str
    ) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/share/{share_id}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get shared chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get shared chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get shared chat: invalid JSON object")
        return data

    def list_all_user_tags(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/all/tags"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list tags failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list tags request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_chats_by_tag_name(
        self,
        acting_uid: str,
        *,
        name: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/tags"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"name": name, "skip": skip, "limit": limit},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats by tag failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats by tag request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_chat_pinned_flag(self, acting_uid: str, chat_id: str) -> bool | None:
        url = f"{self._base}/api/v1/chats/{chat_id}/pinned"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get pinned flag failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get pinned flag request failed: {exc}", transport=True
            ) from exc
        return response.json()  # type: ignore[no-any-return]

    def toggle_chat_pin(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/{chat_id}/pin"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"toggle pin failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"toggle pin request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("toggle pin: invalid JSON object")
        return data

    def toggle_chat_archive(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/{chat_id}/archive"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"toggle archive failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"toggle archive request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("toggle archive: invalid JSON object")
        return data

    def get_chat_tags(self, acting_uid: str, chat_id: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/{chat_id}/tags"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get chat tags failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get chat tags request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def add_chat_tag(self, acting_uid: str, chat_id: str, *, name: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/{chat_id}/tags"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"name": name},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"add chat tag failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"add chat tag request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def delete_chat_tag(self, acting_uid: str, chat_id: str, *, name: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/{chat_id}/tags"
        try:
            response = self._client.request(
                "DELETE",
                url,
                headers=self._acting_headers(acting_uid),
                json={"name": name},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete chat tag failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete chat tag request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def delete_all_chat_tags(self, acting_uid: str, chat_id: str) -> bool:
        url = f"{self._base}/api/v1/chats/{chat_id}/tags/all"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete all chat tags failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete all chat tags request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("delete all chat tags: expected boolean JSON")

    def archive_all_chats(self, acting_uid: str) -> bool:
        url = f"{self._base}/api/v1/chats/archive/all"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"archive all chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"archive all chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("archive all chats: expected boolean JSON")

    def unarchive_all_chats(self, acting_uid: str) -> bool:
        url = f"{self._base}/api/v1/chats/unarchive/all"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"unarchive all chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"unarchive all chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("unarchive all chats: expected boolean JSON")

    def delete_chats_bulk(self, acting_uid: str) -> bool:
        """DELETE /api/v1/chats/ — delete all chats for the acting user."""
        url = f"{self._base}/api/v1/chats/"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete all chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete all chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("delete all chats: expected boolean JSON")

    def list_chats_all(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/all"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats all failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats all request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_chats_all_archived(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/all/archived"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats all archived failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats all archived request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_chats_all_db(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/all/db"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats all db failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats all db request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_chats_folder(self, acting_uid: str, folder_id: str) -> list[dict[str, Any]]:
        fid = quote(folder_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/folder/{fid}"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get chats folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get chats folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_chats_folder(
        self, acting_uid: str, folder_id: str, *, page: int | None = None
    ) -> list[dict[str, Any]]:
        fid = quote(folder_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/folder/{fid}/list"
        params = {"page": page} if page is not None else None
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def import_chats(
        self, acting_uid: str, *, chats: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/chats/import"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json={"chats": chats},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"import chats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"import chats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def list_chats_by_user(
        self,
        acting_uid: str,
        user_id: str,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        uid = quote(user_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/list/user/{uid}"
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if query is not None:
            params["query"] = query
        if order_by is not None:
            params["order_by"] = order_by
        if direction is not None:
            params["direction"] = direction
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list chats by user failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list chats by user request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_chat_stats_usage(
        self,
        acting_uid: str,
        *,
        items_per_page: int | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/stats/usage"
        params: dict[str, Any] = {}
        if items_per_page is not None:
            params["items_per_page"] = items_per_page
        if page is not None:
            params["page"] = page
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"chat stats usage failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"chat stats usage request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("chat stats usage: expected JSON object")
        return data

    def export_chat_stats(
        self,
        acting_uid: str,
        *,
        updated_at: int | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}/api/v1/chats/stats/export"
        params: dict[str, Any] = {"stream": "false"}
        if updated_at is not None:
            params["updated_at"] = updated_at
        if page is not None:
            params["page"] = page
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"export chat stats failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"export chat stats request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("export chat stats: expected JSON object")
        return data

    def stream_export_chat_stats(
        self,
        acting_uid: str,
        *,
        updated_at: int | None = None,
    ) -> OpenWebUIProxyStream:
        """GET /api/v1/chats/stats/export?stream=true — iterate :meth:`OpenWebUIProxyStream.iter_bytes` once."""
        url = f"{self._base}/api/v1/chats/stats/export"
        params: dict[str, Any] = {"stream": "true"}
        if updated_at is not None:
            params["updated_at"] = updated_at
        stream_cm = self._client.stream(
            "GET",
            url,
            headers=self._acting_headers(acting_uid),
            params=params,
        )
        try:
            resp = stream_cm.__enter__()
        except httpx.RequestError as exc:
            with contextlib.suppress(Exception):
                stream_cm.__exit__(type(exc), exc, exc.__traceback__)
            raise OpenWebUIClientError(str(exc), transport=True) from exc
        if resp.status_code >= 400:
            try:
                text = resp.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                text = ""
            with contextlib.suppress(Exception):
                stream_cm.__exit__(None, None, None)
            raise OpenWebUIClientError(
                f"export chat stats stream failed: {resp.status_code} {text}",
                http_status=resp.status_code,
            )
        return OpenWebUIProxyStream(stream_cm, resp)

    def export_chat_stats_by_id(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/stats/export/{cid}"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"export chat stats by id failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"export chat stats by id request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("export chat stats by id: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("export chat stats by id: expected JSON object")
        return data

    def clone_chat(
        self, acting_uid: str, chat_id: str, *, title: str | None = None
    ) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/clone"
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"clone chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"clone chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("clone chat: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("clone chat: expected JSON object")
        return data

    def clone_shared_chat(self, acting_uid: str, share_or_chat_id: str) -> dict[str, Any]:
        sid = quote(share_or_chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{sid}/clone/shared"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"clone shared chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"clone shared chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("clone shared chat: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("clone shared chat: expected JSON object")
        return data

    def move_chat_to_folder(
        self, acting_uid: str, chat_id: str, *, folder_id: str | None
    ) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/folder"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json={"folder_id": folder_id},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"move chat folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"move chat folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("move chat folder: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("move chat folder: expected JSON object")
        return data

    def update_chat_message(
        self, acting_uid: str, chat_id: str, message_id: str, *, content: str
    ) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        mid = quote(message_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/messages/{mid}"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json={"content": content},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update chat message failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update chat message request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("update chat message: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("update chat message: expected JSON object")
        return data

    def create_chat_message_event(
        self,
        acting_uid: str,
        chat_id: str,
        message_id: str,
        *,
        event_type: str,
        data: dict[str, Any],
    ) -> bool:
        cid = quote(chat_id.strip(), safe="")
        mid = quote(message_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/messages/{mid}/event"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json={"type": event_type, "data": data},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"chat message event failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"chat message event request failed: {exc}", transport=True
            ) from exc
        out = response.json()
        if out is True:
            return True
        if out is False:
            return False
        raise OpenWebUIClientError("chat message event: expected boolean JSON")

    def delete_chat_share(self, acting_uid: str, chat_id: str) -> bool | None:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/share"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete chat share failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete chat share request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is True:
            return True
        if data is False:
            return False
        return None

    def create_chat_share(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/v1/chats/{cid}/share"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"create chat share failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"create chat share request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("create chat share: unexpected null")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("create chat share: expected JSON object")
        return data

    def memories_list(self, acting_uid: str) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v1/memories/"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"memories list failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"memories list request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def memories_add(self, acting_uid: str, *, content: str) -> dict[str, Any] | None:
        url = f"{self._base}/api/v1/memories/add"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"content": content},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"memories add failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"memories add request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            return None
        if isinstance(data, dict):
            return data
        raise OpenWebUIClientError("memories add: invalid JSON object")

    def memories_query(
        self, acting_uid: str, *, content: str, k: int | None
    ) -> Any:
        url = f"{self._base}/api/v1/memories/query"
        payload: dict[str, Any] = {"content": content}
        if k is not None:
            payload["k"] = k
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"memories query failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"memories query request failed: {exc}", transport=True
            ) from exc
        return response.json()

    def memories_reset(self, acting_uid: str) -> bool:
        url = f"{self._base}/api/v1/memories/reset"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"memories reset failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"memories reset request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "memories reset: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("memories reset: expected boolean JSON")

    def memories_update(
        self, acting_uid: str, memory_id: str, *, content: str
    ) -> dict[str, Any] | None:
        safe_id = quote(str(memory_id).strip(), safe="-._~")
        url = f"{self._base}/api/v1/memories/{safe_id}/update"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json={"content": content},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"memories update failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"memories update request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            return None
        if isinstance(data, dict):
            return data
        raise OpenWebUIClientError("memories update: invalid JSON object")

    def list_prompts(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /api/v1/prompts/ — list readable prompts for the acting user."""
        url = f"{self._base}/api/v1/prompts/"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list prompts failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list prompts request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_prompt_list(
        self,
        acting_uid: str,
        *,
        query: str | None = None,
        view_option: str | None = None,
        tag: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/prompts/list — paginated search (Open WebUI query params)."""
        url = f"{self._base}/api/v1/prompts/list"
        params: dict[str, Any] = {}
        if query is not None:
            params["query"] = query
        if view_option is not None:
            params["view_option"] = view_option
        if tag is not None:
            params["tag"] = tag
        if order_by is not None:
            params["order_by"] = order_by
        if direction is not None:
            params["direction"] = direction
        if page is not None:
            params["page"] = page
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"prompt list failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"prompt list request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("prompt list: invalid JSON object")
        return data

    def get_prompt_by_command(self, acting_uid: str, command: str) -> dict[str, Any]:
        enc = quote(command, safe="")
        url = f"{self._base}/api/v1/prompts/command/{enc}"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get prompt by command failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get prompt by command request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("prompt: empty response", http_status=404)
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get prompt by command: invalid JSON object")
        return data

    def get_prompt_by_id(self, acting_uid: str, prompt_id: str) -> dict[str, Any]:
        enc = quote(prompt_id, safe="")
        url = f"{self._base}/api/v1/prompts/id/{enc}"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get prompt failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get prompt request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("prompt: empty response", http_status=404)
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get prompt: invalid JSON object")
        return data

    def update_prompt(
        self, acting_uid: str, prompt_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /api/v1/prompts/id/{id}/update — full prompt form (Open WebUI ``PromptForm``)."""
        enc = quote(prompt_id, safe="")
        url = f"{self._base}/api/v1/prompts/id/{enc}/update"
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update prompt failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update prompt request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            raise OpenWebUIClientError("update prompt: empty response")
        if not isinstance(data, dict):
            raise OpenWebUIClientError("update prompt: invalid JSON object")
        return data

    def delete_prompt(self, acting_uid: str, prompt_id: str) -> bool:
        """DELETE /api/v1/prompts/id/{id}/delete — returns OW JSON boolean."""
        enc = quote(prompt_id, safe="")
        url = f"{self._base}/api/v1/prompts/id/{enc}/delete"
        try:
            response = self._client.delete(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete prompt failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete prompt request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "delete prompt: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if data is True:
            return True
        if data is False:
            return False
        raise OpenWebUIClientError("delete prompt: expected boolean JSON")


    def list_models_workspace(
        self,
        acting_uid: str,
        *,
        query: str | None = None,
        view_option: str | None = None,
        tag: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/models/list — paginated workspace models for the acting user."""
        url = f"{self._base}/api/v1/models/list"
        params: dict[str, Any] = {}
        if query is not None and query != "":
            params["query"] = query
        if view_option is not None and view_option != "":
            params["view_option"] = view_option
        if tag is not None and tag != "":
            params["tag"] = tag
        if order_by is not None and order_by != "":
            params["order_by"] = order_by
        if direction is not None and direction != "":
            params["direction"] = direction
        if page is not None:
            params["page"] = page
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list models failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list models request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list models: expected JSON object")
        return data

    def get_models_base(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /api/v1/models/base — Open WebUI restricts this to admin users upstream."""
        url = f"{self._base}/api/v1/models/base"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get base models failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get base models request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            raise OpenWebUIClientError("get base models: expected JSON array")
        return [x for x in data if isinstance(x, dict)]

    def get_model_tags(self, acting_uid: str) -> list[str]:
        """GET /api/v1/models/tags."""
        url = f"{self._base}/api/v1/models/tags"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get model tags failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get model tags request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            raise OpenWebUIClientError("get model tags: expected JSON array")
        out: list[str] = []
        for x in data:
            if isinstance(x, str):
                out.append(x)
            elif x is not None:
                out.append(str(x))
        return out

    def get_model_by_id(self, acting_uid: str, model_id: str) -> dict[str, Any] | None:
        """GET /api/v1/models/model?id=... — OW uses query param so ``/`` may appear in ids."""
        url = f"{self._base}/api/v1/models/model"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params={"id": model_id},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get model failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get model request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            return None
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get model: expected JSON object or null")
        return data

    def list_tools(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /api/v1/tools/list — tool rows with access flags."""
        url = f"{self._base}/api/v1/tools/list"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list tools failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list tools request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_tool(self, acting_uid: str, tool_id: str) -> dict[str, Any]:
        """GET /api/v1/tools/id/{id}."""
        url = f"{self._base}/api/v1/tools/id/{tool_id}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get tool failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get tool request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get tool: invalid JSON object")
        return data

    def get_tool_valves(self, acting_uid: str, tool_id: str) -> dict[str, Any] | None:
        """GET /api/v1/tools/id/{id}/valves — may be JSON null."""
        url = f"{self._base}/api/v1/tools/id/{tool_id}/valves"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get tool valves failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get tool valves request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            return None
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get tool valves: expected JSON object or null")
        return data

    def update_tool_valves(
        self, acting_uid: str, tool_id: str, body: dict[str, Any]
    ) -> dict[str, Any] | None:
        """POST /api/v1/tools/id/{id}/valves/update — JSON object body."""
        url = f"{self._base}/api/v1/tools/id/{tool_id}/valves/update"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update tool valves failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update tool valves request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if data is None:
            return None
        if not isinstance(data, dict):
            raise OpenWebUIClientError("update tool valves: expected JSON object or null")
        return data

    def get_configs_get_json(self, acting_uid: str, config_key: str) -> Any:
        """GET ``/api/v1/configs/{config_key}`` — *config_key* must be in ``OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS``."""
        from app.lib.openwebui_safe_config import OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS

        if config_key not in OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS:
            raise ValueError(
                f"get_configs_get_json: disallowed config_key {config_key!r} "
                "(use platform whitelist only)"
            )
        url = f"{self._base}/api/v1/configs/{config_key}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get configs failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get configs request failed: {exc}", transport=True
            ) from exc
        try:
            return response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "get configs: response is not valid JSON",
                http_status=response.status_code,
            ) from exc

    def get_session_user(self, acting_uid: str) -> dict[str, Any]:
        """Resolve current session user for the acting uid (Open WebUI auths session GET)."""
        url = f"{self._base}/api/v1/auths/"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"session user failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"session user request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "session user: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise OpenWebUIClientError("session user: expected JSON object")
        return data

    def list_folders(self, acting_uid: str) -> list[dict[str, Any]]:
        """GET /api/v1/folders/ — summary rows (id, name, meta, parent_id, …)."""
        url = f"{self._base}/api/v1/folders/"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list folders failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list folders request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_folder(self, acting_uid: str, folder_id: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/folders/{folder_id}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get folder: invalid JSON object")
        return data

    def create_folder(self, acting_uid: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/api/v1/folders/"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"create folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"create folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("create folder: invalid response")
        return data

    def update_folder(
        self, acting_uid: str, folder_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"{self._base}/api/v1/folders/{folder_id}/update"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update folder request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("update folder: invalid response")
        return data

    def delete_folder(
        self, acting_uid: str, folder_id: str, *, delete_contents: bool = True
    ) -> None:
        url = f"{self._base}/api/v1/folders/{folder_id}"
        try:
            response = self._client.delete(
                url,
                headers=self._acting_headers(acting_uid),
                params={"delete_contents": delete_contents},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"delete folder failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"delete folder request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "delete folder: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if data is not True:
            raise OpenWebUIClientError("delete folder: expected true JSON")

    def list_skills(self, acting_uid: str) -> Any:
        """GET /api/v1/skills/ — returns parsed JSON (list or object, per downstream)."""
        url = f"{self._base}/api/v1/skills/"
        return self._get_json_any(acting_uid, url, "list skills")

    def get_skill(self, acting_uid: str, skill_id: str) -> Any:
        """GET /api/v1/skills/id/{id}"""
        sid = quote(str(skill_id).strip(), safe="")
        if not sid:
            raise OpenWebUIClientError("get skill: empty id")
        url = f"{self._base}/api/v1/skills/id/{sid}"
        return self._get_json_any(acting_uid, url, "get skill")

    def list_functions(self, acting_uid: str) -> Any:
        """GET /api/v1/functions/ — returns parsed JSON (list or object, per downstream)."""
        url = f"{self._base}/api/v1/functions/"
        return self._get_json_any(acting_uid, url, "list functions")

    def get_function(self, acting_uid: str, function_id: str) -> Any:
        """GET /api/v1/functions/id/{id}"""
        fid = quote(str(function_id).strip(), safe="")
        if not fid:
            raise OpenWebUIClientError("get function: empty id")
        url = f"{self._base}/api/v1/functions/id/{fid}"
        return self._get_json_any(acting_uid, url, "get function")

    def _get_json_any(self, acting_uid: str, url: str, label: str) -> Any:
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"{label} failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"{label} request failed: {exc}", transport=True
            ) from exc
        try:
            return response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                f"{label}: response is not valid JSON",
                http_status=response.status_code,
            ) from exc

    def list_notes(self, acting_uid: str, *, page: int | None = None) -> list[dict[str, Any]]:
        """GET /api/v1/notes/ — optional ``page`` (1-based), matches fork router."""
        url = f"{self._base}/api/v1/notes/"
        params: dict[str, int] = {}
        if page is not None:
            params["page"] = page
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params or None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list notes failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list notes request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def get_note(self, acting_uid: str, note_id: str) -> dict[str, Any]:
        """GET /api/v1/notes/{id} — matches fork ``get_note_by_id``."""
        url = f"{self._base}/api/v1/notes/{note_id}"
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get note failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get note request failed: {exc}", transport=True
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise OpenWebUIClientError(
                "get note: response is not valid JSON",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get note: invalid JSON object")
        return data


    def get_version(self) -> dict[str, Any]:
        url = f"{self._base}/api/version"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get version failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get version request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get version: expected JSON object")
        return data

    def get_version_updates(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/version/updates"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get version updates failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get version updates request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get version updates: expected JSON object")
        return data

    def get_changelog(self) -> dict[str, Any]:
        url = f"{self._base}/api/changelog"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get changelog failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get changelog request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get changelog: expected JSON object")
        return data

    def get_health(self) -> dict[str, Any]:
        url = f"{self._base}/health"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get health failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get health request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get health: expected JSON object")
        return data

    def get_health_db(self) -> dict[str, Any]:
        url = f"{self._base}/health/db"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get health db failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get health db request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get health db: expected JSON object")
        return data

    def get_manifest(self) -> dict[str, Any]:
        url = f"{self._base}/manifest.json"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get manifest failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get manifest request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get manifest: expected JSON object")
        return data

    def get_config(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/config"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get app config failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get app config request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get app config: expected JSON object")
        return data

    def get_usage(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/usage"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get usage failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get usage request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get usage: expected JSON object")
        return data

    def list_tasks(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/tasks"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list tasks failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list tasks request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list tasks: expected JSON object")
        return data

    def get_task_chat(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        cid = quote(chat_id.strip(), safe="")
        url = f"{self._base}/api/tasks/chat/{cid}"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get task chat failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get task chat request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get task chat: expected JSON object")
        return data

    def stop_task(self, acting_uid: str, task_id: str) -> Any:
        tid = quote(task_id.strip(), safe="")
        url = f"{self._base}/api/tasks/stop/{tid}"
        try:
            response = self._client.post(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"stop task failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"stop task request failed: {exc}", transport=True
            ) from exc
        try:
            return response.json()
        except Exception:
            return None

    def get_audio_config(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/audio/config"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"get audio config failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"get audio config request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("get audio config: expected JSON object")
        return data

    def update_audio_config(self, acting_uid: str, body: dict[str, Any]) -> Any:
        url = f"{self._base}/api/v1/audio/config/update"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"update audio config failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"update audio config request failed: {exc}", transport=True
            ) from exc
        try:
            return response.json()
        except Exception:
            return {"ok": True}

    def list_audio_models(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/audio/models"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list audio models failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list audio models request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list audio models: expected JSON object")
        return data

    def list_audio_voices(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/v1/audio/voices"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list audio voices failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list audio voices request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list audio voices: expected JSON object")
        return data

    def create_audio_speech(self, acting_uid: str, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._base}/api/v1/audio/speech"
        try:
            response = self._client.post(
                url,
                headers={
                    **self._acting_headers(acting_uid),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"audio speech failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"audio speech request failed: {exc}", transport=True
            ) from exc
        return response

    def create_audio_transcription(
        self,
        acting_uid: str,
        *,
        file_content: bytes,
        filename: str,
        content_type: str | None,
        language: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}/api/v1/audio/transcriptions"
        ct = content_type or "application/octet-stream"
        files = {"file": (filename, file_content, ct)}
        data: dict[str, str] | None = None
        if language is not None:
            data = {"language": language}
        try:
            response = self._client.post(
                url,
                headers=self._acting_headers(acting_uid),
                files=files,
                data=data,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"audio transcription failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"audio transcription request failed: {exc}", transport=True
            ) from exc
        out = response.json()
        if not isinstance(out, dict):
            raise OpenWebUIClientError("audio transcription: expected JSON object")
        return out


    def list_models_legacy(self, acting_uid: str, *, refresh: bool = False) -> dict[str, Any]:
        url = f"{self._base}/api/models"
        params = {"refresh": "true"} if refresh else None
        try:
            response = self._client.get(
                url,
                headers=self._acting_headers(acting_uid),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list models legacy failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list models legacy request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list models legacy: expected JSON object")
        return data

    def list_models_base_legacy(self, acting_uid: str) -> dict[str, Any]:
        url = f"{self._base}/api/models/base"
        try:
            response = self._client.get(url, headers=self._acting_headers(acting_uid))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OpenWebUIClientError(
                f"list models base legacy failed: {exc.response.status_code} {exc.response.text[:500]}",
                http_status=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(
                f"list models base legacy request failed: {exc}", transport=True
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise OpenWebUIClientError("list models base legacy: expected JSON object")
        return data

    def _proxy_forward_headers(
        self, acting_uid: str | None, extra: dict[str, str] | None
    ) -> dict[str, str]:
        hdrs: dict[str, str] = (
            dict(self._acting_headers(acting_uid)) if acting_uid else {}
        )
        if not extra:
            return hdrs
        skip = frozenset(
            {
                "host",
                "content-length",
                "transfer-encoding",
                "connection",
                self._acting_header.lower(),
            }
        )
        for k, v in extra.items():
            if k.lower() in skip:
                continue
            hdrs[k] = v
        return hdrs

    def proxy_to_openwebui(
        self,
        acting_uid: str | None,
        *,
        method: str,
        downstream_path: str,
        params: list[tuple[str, str]] | dict[str, Any] | None = None,
        content: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Forward to Open WebUI; returns raw response (any status). Caller reads body."""
        path = downstream_path if downstream_path.startswith("/") else f"/{downstream_path}"
        url = f"{self._base}{path}"
        hdrs = self._proxy_forward_headers(acting_uid, extra_headers)
        try:
            return self._client.request(
                method.upper(),
                url,
                headers=hdrs,
                params=params,
                content=content,
            )
        except httpx.RequestError as exc:
            raise OpenWebUIClientError(str(exc), transport=True) from exc

    def proxy_to_openwebui_stream(
        self,
        acting_uid: str | None,
        *,
        method: str,
        downstream_path: str,
        params: list[tuple[str, str]] | dict[str, Any] | None = None,
        content: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> OpenWebUIProxyStream:
        """Stream from Open WebUI. Raises OpenWebUIClientError if upstream status is >= 400."""
        path = downstream_path if downstream_path.startswith("/") else f"/{downstream_path}"
        url = f"{self._base}{path}"
        hdrs = self._proxy_forward_headers(acting_uid, extra_headers)
        stream_cm = self._client.stream(
            method.upper(),
            url,
            headers=hdrs,
            params=params,
            content=content,
        )
        try:
            resp = stream_cm.__enter__()
        except httpx.RequestError as exc:
            with contextlib.suppress(Exception):
                stream_cm.__exit__(type(exc), exc, exc.__traceback__)
            raise OpenWebUIClientError(str(exc), transport=True) from exc
        except BaseException:
            with contextlib.suppress(Exception):
                stream_cm.__exit__(*sys.exc_info())
            raise
        try:
            if resp.status_code >= 400:
                body_text = resp.text
                stream_cm.__exit__(None, None, None)
                raise OpenWebUIClientError(
                    body_text[:500] if body_text else "upstream error",
                    http_status=resp.status_code,
                )
            return OpenWebUIProxyStream(stream_cm, resp)
        except OpenWebUIClientError:
            raise
        except BaseException:
            with contextlib.suppress(Exception):
                stream_cm.__exit__(None, None, None)
            raise

