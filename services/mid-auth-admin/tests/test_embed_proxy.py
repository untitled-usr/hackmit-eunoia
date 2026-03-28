from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mid_auth_admin.main import app


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "ChangeMe123!"},
    )
    assert response.status_code == 200


def test_embed_proxy_http_rewrite_headers() -> None:
    os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.local"
    client = TestClient(app)
    _login(client)

    async def fake_request(self, method: str, url: str, **kwargs):  # type: ignore[no-untyped-def]
        assert method == "GET"
        assert url == "http://openwebui.local/api/v1/users?q=test"
        assert "host" not in {k.lower() for k in kwargs["headers"].keys()}
        return httpx.Response(
            status_code=302,
            headers={
                "Location": "http://openwebui.local/login",
                "Set-Cookie": "sid=abc; Path=/; HttpOnly; Domain=openwebui.local",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'",
            },
            text="redirect",
        )

    with patch("httpx.AsyncClient.request", new=fake_request):
        response = client.get("/embed/openwebui/api/v1/users?q=test", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/embed/openwebui/login"
    assert "x-frame-options" not in {k.lower() for k in response.headers.keys()}
    assert "frame-ancestors 'self'" in response.headers.get("content-security-policy", "")
    set_cookie = response.headers.get("set-cookie", "")
    assert "Path=/embed/openwebui" in set_cookie
    assert "Domain=" not in set_cookie


def test_embed_proxy_websocket_requires_auth() -> None:
    os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.local"
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/embed/openwebui/ws/stream"):
            pass
    assert exc.value.code in {1008, 1011}

