from __future__ import annotations

from typing import Any

from mid_auth_admin.integrations.platform_client_base import (
    PlatformActionNotSupported,
    PlatformClientBase,
)
from mid_auth_admin.schemas.platform_users import (
    PlatformUserCreateRequest,
    PlatformUserPatchRequest,
    PlatformUserRecord,
)


def _memos_id(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("users/"):
        return stripped.split("/", 1)[1]
    return stripped


class MemosAdminClient(PlatformClientBase):
    def list_users(self, *, q: str | None, limit: int, offset: int) -> list[PlatformUserRecord]:
        params: dict[str, Any] = {"pageSize": limit, "pageToken": str(offset)}
        if q:
            params["filter"] = q
        data = self._request("GET", "/api/v1/users", params=params)
        if not isinstance(data, dict):
            return []
        users = data.get("users")
        if not isinstance(users, list):
            return []
        return [self._as_record(u) for u in users if isinstance(u, dict)]

    def get_user(self, *, user_id: str) -> PlatformUserRecord:
        data = self._request("GET", f"/api/v1/users/{_memos_id(user_id)}")
        if not isinstance(data, dict):
            return PlatformUserRecord(id=user_id, raw={})
        return self._as_record(data)

    def create_user(self, *, payload: PlatformUserCreateRequest) -> PlatformUserRecord:
        body: dict[str, Any] = payload.raw or {}
        data = self._request("POST", "/api/v1/users", json_body=body)
        if not isinstance(data, dict):
            return PlatformUserRecord(id="", raw={})
        return self._as_record(data)

    def update_user_profile(
        self, *, user_id: str, payload: PlatformUserPatchRequest
    ) -> PlatformUserRecord:
        body = dict(payload.raw)
        if payload.email is not None:
            body["email"] = payload.email
        if payload.display_name is not None:
            body["nickname"] = payload.display_name
        if payload.password is not None:
            body["password"] = payload.password
        data = self._request(
            "PATCH",
            f"/api/v1/users/{_memos_id(user_id)}",
            params={"updateMask": ",".join(body.keys()) if body else "nickname"},
            json_body=body or {"nickname": ""},
        )
        if not isinstance(data, dict):
            return PlatformUserRecord(id=user_id, raw={})
        return self._as_record(data)

    def set_user_enabled(self, *, user_id: str, enabled: bool) -> PlatformUserRecord:
        raise PlatformActionNotSupported("enable_disable", self.platform)

    def delete_user(self, *, user_id: str) -> None:
        self._request("DELETE", f"/api/v1/users/{_memos_id(user_id)}")

