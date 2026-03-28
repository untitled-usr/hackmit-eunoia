from __future__ import annotations

from typing import Any

from mid_auth_admin.integrations.platform_client_base import PlatformClientBase
from mid_auth_admin.schemas.platform_users import (
    PlatformUserCreateRequest,
    PlatformUserPatchRequest,
    PlatformUserRecord,
)


class OpenWebUIAdminClient(PlatformClientBase):
    def list_users(self, *, q: str | None, limit: int, offset: int) -> list[PlatformUserRecord]:
        params: dict[str, Any] = {"page": max(1, (offset // max(limit, 1)) + 1)}
        if q:
            params["query"] = q
        data = self._request("GET", "/api/v1/users", params=params)
        if isinstance(data, list):
            return [self._as_record(u) for u in data if isinstance(u, dict)]
        if isinstance(data, dict):
            items = data.get("users")
            if isinstance(items, list):
                return [self._as_record(u) for u in items if isinstance(u, dict)]
        return []

    def get_user(self, *, user_id: str) -> PlatformUserRecord:
        data = self._request("GET", f"/api/v1/users/{user_id}")
        if not isinstance(data, dict):
            return PlatformUserRecord(id=user_id, raw={})
        return self._as_record(data)

    def create_user(self, *, payload: PlatformUserCreateRequest) -> PlatformUserRecord:
        body: dict[str, Any] = {
            "name": payload.display_name or payload.username or "new-user",
            "username": payload.username or payload.email or "new-user",
            "email": payload.email or "",
            "password": payload.password or "ChangeMe123!",
            "profile_image_url": "/user.png",
        }
        body.update(payload.raw)
        data = self._request("POST", "/api/v1/auths/register", json_body=body)
        if not isinstance(data, dict):
            return PlatformUserRecord(id="", raw={})
        return self._as_record(data)

    def update_user_profile(
        self, *, user_id: str, payload: PlatformUserPatchRequest
    ) -> PlatformUserRecord:
        body = dict(payload.raw)
        if payload.display_name is not None:
            body["name"] = payload.display_name
        if payload.email is not None:
            body["email"] = payload.email
        if payload.password is not None:
            body["password"] = payload.password
        data = self._request("PATCH", f"/api/v1/users/{user_id}", json_body=body)
        if not isinstance(data, dict):
            return PlatformUserRecord(id=user_id, raw={})
        return self._as_record(data)

    def set_user_enabled(self, *, user_id: str, enabled: bool) -> PlatformUserRecord:
        data = self._request("PATCH", f"/api/v1/users/{user_id}", json_body={"active": enabled})
        if not isinstance(data, dict):
            return PlatformUserRecord(id=user_id, is_active=enabled, raw={})
        record = self._as_record(data)
        if record.is_active is None:
            record.is_active = enabled
        return record

    def delete_user(self, *, user_id: str) -> None:
        self._request("DELETE", f"/api/v1/users/{user_id}")

