from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mid_auth_admin.integrations.memos_admin_client import MemosAdminClient
from mid_auth_admin.integrations.openwebui_admin_client import OpenWebUIAdminClient
from mid_auth_admin.integrations.platform_client_base import PlatformActionNotSupported
from mid_auth_admin.integrations.vocechat_admin_client import VoceChatAdminClient
from mid_auth_admin.main import app
from mid_auth_admin.schemas.platform_users import (
    PlatformUserCreateRequest,
    PlatformUserPatchRequest,
)
from mid_auth_admin.services.platform_user_admin_service import PlatformUserAdminService


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "ChangeMe123!"},
    )
    assert response.status_code == 200


def test_openwebui_client_crud_and_header_injection() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("X-Acting-Uid")))
        if request.method == "GET" and request.url.path == "/api/v1/users":
            return httpx.Response(200, json=[{"id": "u1", "name": "User1", "email": "u1@test.local"}])
        if request.method == "GET" and request.url.path == "/api/v1/users/u1":
            return httpx.Response(200, json={"id": "u1", "name": "User1"})
        if request.method == "POST" and request.url.path == "/api/v1/auths/register":
            return httpx.Response(200, json={"id": "u2", "name": "NewUser"})
        if request.method == "PATCH" and request.url.path == "/api/v1/users/u1":
            return httpx.Response(200, json={"id": "u1", "name": "Renamed", "active": True})
        if request.method == "DELETE" and request.url.path == "/api/v1/users/u1":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "not found"})

    client = OpenWebUIAdminClient(
        platform="openwebui",
        base_url="http://ow.local",
        acting_uid_header="X-Acting-Uid",
        acting_uid_value="00000000-0000-4000-8000-000000000001",
        transport=httpx.MockTransport(handler),
    )
    rows = client.list_users(q=None, limit=20, offset=0)
    assert len(rows) == 1 and rows[0].id == "u1"
    assert client.get_user(user_id="u1").id == "u1"
    created = client.create_user(payload=PlatformUserCreateRequest(username="new"))
    assert created.id == "u2"
    patched = client.update_user_profile(
        user_id="u1", payload=PlatformUserPatchRequest(display_name="Renamed")
    )
    assert patched.id == "u1"
    enabled = client.set_user_enabled(user_id="u1", enabled=True)
    assert enabled.id == "u1"
    client.delete_user(user_id="u1")
    assert all(h == "00000000-0000-4000-8000-000000000001" for _, _, h in seen)


def test_memos_client_header_and_enable_not_supported() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("X-Acting-Uid"))
        if request.method == "GET" and request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"users": [{"name": "users/2", "nickname": "Nick"}]})
        if request.method == "GET" and request.url.path == "/api/v1/users/2":
            return httpx.Response(200, json={"name": "users/2", "nickname": "Nick"})
        if request.method == "POST" and request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"name": "users/3", "username": "u3"})
        if request.method == "PATCH" and request.url.path == "/api/v1/users/2":
            return httpx.Response(200, json={"name": "users/2", "nickname": "Nick2"})
        if request.method == "DELETE" and request.url.path == "/api/v1/users/2":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "not found"})

    client = MemosAdminClient(
        platform="memos",
        base_url="http://memos.local",
        acting_uid_header="X-Acting-Uid",
        acting_uid_value="1",
        transport=httpx.MockTransport(handler),
    )
    assert client.list_users(q=None, limit=20, offset=0)[0].id == "users/2"
    assert client.get_user(user_id="2").id == "users/2"
    assert client.create_user(payload=PlatformUserCreateRequest()).id == "users/3"
    assert (
        client.update_user_profile(user_id="2", payload=PlatformUserPatchRequest(display_name="Nick2")).id
        == "users/2"
    )
    client.delete_user(user_id="2")
    with pytest.raises(PlatformActionNotSupported):
        client.set_user_enabled(user_id="2", enabled=False)
    assert all(h == "1" for h in seen)


def test_vocechat_client_create_get_delete_and_service_guards() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.method == "POST" and request.url.path == "/api/user/register":
            return httpx.Response(200, json={"uid": 7, "name": "vc-user"})
        if request.method == "GET" and request.url.path == "/api/bot/user/7":
            return httpx.Response(200, json={"uid": 7, "name": "vc-user"})
        if request.method == "DELETE" and request.url.path == "/api/admin/user/7":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "not found"})

    vc_client = VoceChatAdminClient(
        platform="vocechat",
        base_url="http://vc.local/api",
        acting_uid_header="X-Acting-Uid",
        acting_uid_value="1",
        transport=httpx.MockTransport(handler),
    )
    assert vc_client.create_user(payload=PlatformUserCreateRequest(username="vc")).id == "7"
    assert vc_client.get_user(user_id="7").id == "7"
    vc_client.delete_user(user_id="7")
    assert "/api/admin/user/7" in seen_paths

    service = PlatformUserAdminService(
        vocechat=vc_client,
        memos=vc_client,  # unused in this assertion
        openwebui=vc_client,  # unused in this assertion
    )
    with pytest.raises(HTTPException) as exc:
        service.delete_user(platform="vocechat", user_id="1")
    assert exc.value.status_code == 409


def test_platform_users_router_smoke_with_override() -> None:
    class FakeService:
        def list_users(self, *, platform: str, q: str | None, limit: int, offset: int) -> dict[str, Any]:
            return {"platform": platform, "limit": limit, "offset": offset, "items": []}

        def get_user(self, *, platform: str, user_id: str) -> dict[str, Any]:
            return {"id": user_id, "raw": {}, "username": None, "display_name": None, "email": None, "is_active": None}

        def create_user(self, *, platform: str, payload: PlatformUserCreateRequest) -> dict[str, Any]:
            return {
                "id": payload.username or "new",
                "raw": {},
                "username": payload.username,
                "display_name": payload.display_name,
                "email": payload.email,
                "is_active": None,
            }

        def update_user(
            self, *, platform: str, user_id: str, payload: PlatformUserPatchRequest
        ) -> dict[str, Any]:
            return {"id": user_id, "raw": payload.raw, "username": None, "display_name": None, "email": None, "is_active": payload.is_active}

        def delete_user(self, *, platform: str, user_id: str) -> None:
            return None

    from mid_auth_admin.services.platform_user_admin_service import get_platform_user_admin_service

    app.dependency_overrides[get_platform_user_admin_service] = lambda: FakeService()
    try:
        client = TestClient(app)
        _login(client)
        assert client.get("/admin/platform-users/openwebui").status_code == 200
        assert client.get("/admin/platform-users/openwebui/u1").status_code == 200
        assert client.post("/admin/platform-users/openwebui", json={"username": "new"}).status_code == 201
        assert client.patch("/admin/platform-users/openwebui/u1", json={"display_name": "x"}).status_code == 200
        assert client.delete("/admin/platform-users/openwebui/u1").status_code == 204
    finally:
        app.dependency_overrides.clear()

