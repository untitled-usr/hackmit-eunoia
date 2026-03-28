from __future__ import annotations

from typing import Any

from mid_auth_admin.integrations.platform_client_base import (
    PlatformActionNotSupported,
    PlatformClientBase,
)
from mid_auth_admin.schemas.platform_users import (
    PlatformUserCreateRequest,
    PlatformUserRecord,
)


class VoceChatAdminClient(PlatformClientBase):
    def list_users(self, *, q: str | None, limit: int, offset: int) -> list[PlatformUserRecord]:
        raise PlatformActionNotSupported("list", self.platform)

    def get_user(self, *, user_id: str) -> PlatformUserRecord:
        data = self._request("GET", f"/bot/user/{int(user_id)}")
        if not isinstance(data, dict):
            return PlatformUserRecord(id=str(user_id), raw={})
        return self._as_record(data)

    def create_user(self, *, payload: PlatformUserCreateRequest) -> PlatformUserRecord:
        body: dict[str, Any] = {
            "password": (payload.password or "ChangeMe123!"),
            "name": (payload.username or payload.display_name or "new-user")[:32],
            "language": "en-US",
            "gender": 0,
            "device": "mid-auth-admin",
        }
        data = self._request("POST", "/user/register", json_body=body)
        if not isinstance(data, dict):
            return PlatformUserRecord(id="", raw={})
        return self._as_record(data)

    def delete_user(self, *, user_id: str) -> None:
        self._request("DELETE", f"/admin/user/{int(user_id)}")

