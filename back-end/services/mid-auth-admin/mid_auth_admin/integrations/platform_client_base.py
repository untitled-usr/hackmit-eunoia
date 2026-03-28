from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from mid_auth_admin.schemas.platform_users import (
    PlatformUserCreateRequest,
    PlatformUserPatchRequest,
    PlatformUserRecord,
)


@dataclass
class DownstreamHttpError(Exception):
    message: str
    status_code: int | None = None


class PlatformActionNotSupported(Exception):
    def __init__(self, action: str, platform: str) -> None:
        super().__init__(f"{platform} does not support action: {action}")
        self.action = action
        self.platform = platform


class PlatformClientBase:
    def __init__(
        self,
        *,
        platform: str,
        base_url: str,
        acting_uid_header: str,
        acting_uid_value: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.platform = platform
        self.base_url = base_url.rstrip("/")
        self.acting_uid_header = acting_uid_header
        self.acting_uid_value = acting_uid_value
        self.client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        return {
            self.acting_uid_header: self.acting_uid_value,
            "Accept": "application/json",
        }

    @staticmethod
    def _as_record(data: dict[str, Any]) -> PlatformUserRecord:
        return PlatformUserRecord(
            id=str(data.get("id") or data.get("uid") or data.get("name") or ""),
            username=data.get("username") if isinstance(data.get("username"), str) else None,
            display_name=(
                data.get("display_name")
                if isinstance(data.get("display_name"), str)
                else (data.get("name") if isinstance(data.get("name"), str) else None)
            ),
            email=data.get("email") if isinstance(data.get("email"), str) else None,
            is_active=data.get("is_active") if isinstance(data.get("is_active"), bool) else None,
            raw=data,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=self._headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DownstreamHttpError(
                f"{self.platform} {method} {path} failed: {exc.response.status_code} "
                f"{exc.response.text[:500]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise DownstreamHttpError(
                f"{self.platform} {method} {path} request error: {exc}",
                status_code=503,
            ) from exc
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return {"text": response.text}

    def list_users(self, *, q: str | None, limit: int, offset: int) -> list[PlatformUserRecord]:
        raise PlatformActionNotSupported("list", self.platform)

    def get_user(self, *, user_id: str) -> PlatformUserRecord:
        raise PlatformActionNotSupported("get", self.platform)

    def create_user(self, *, payload: PlatformUserCreateRequest) -> PlatformUserRecord:
        raise PlatformActionNotSupported("create", self.platform)

    def update_user_profile(
        self, *, user_id: str, payload: PlatformUserPatchRequest
    ) -> PlatformUserRecord:
        raise PlatformActionNotSupported("update_profile", self.platform)

    def set_user_enabled(self, *, user_id: str, enabled: bool) -> PlatformUserRecord:
        raise PlatformActionNotSupported("enable_disable", self.platform)

    def delete_user(self, *, user_id: str) -> None:
        raise PlatformActionNotSupported("delete", self.platform)

