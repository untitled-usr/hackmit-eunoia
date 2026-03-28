"""Anti-leak guardrails: proxy error mapping, response header allowlists."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_anti_leak.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"
os.environ["MID_AUTH_VOCECHAT_BASE_URL"] = "http://vocechat.test/api"
os.environ["MID_AUTH_MEMOS_BASE_URL"] = "http://memos.test"

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.proxy_safety import filter_allowlisted_proxy_response_headers
from app.db.base import Base
from app.db.session import engine
from app.integrations.openwebui_client import (
    OpenWebUIClientError,
    filter_openwebui_proxy_response_headers,
)
from app.main import app
from app.services.openwebui_root_proxy_service import map_openwebui_proxy_client_error

DB_FILE = Path("/tmp/mid_auth_anti_leak.db")


class AntiLeakGuardrailsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(bind=engine)

    def test_map_proxy_error_never_echoes_downstream_body(self) -> None:
        exc = OpenWebUIClientError(
            "INTERNAL_SECRET http://openwebui.internal:8080/api/v1/leak",
            http_status=400,
        )
        http_exc = map_openwebui_proxy_client_error(exc)
        self.assertIsInstance(http_exc, HTTPException)
        self.assertEqual(http_exc.status_code, 400)
        self.assertEqual(http_exc.detail, "openwebui request rejected")
        self.assertNotIn("8080", str(http_exc.detail))
        self.assertNotIn("INTERNAL", str(http_exc.detail))

    def test_map_proxy_error_transport_generic(self) -> None:
        exc = OpenWebUIClientError("ConnectError http://10.0.0.5:9999", transport=True)
        http_exc = map_openwebui_proxy_client_error(exc)
        self.assertEqual(http_exc.status_code, 503)
        self.assertEqual(http_exc.detail, "openwebui upstream unavailable")

    def test_allowlisted_headers_drop_set_cookie_and_location(self) -> None:
        h = httpx.Headers(
            [
                ("Content-Type", "application/json"),
                ("Set-Cookie", "session=evil; Path=/"),
                ("Location", "http://internal-openwebui/v1/x"),
                ("X-Internal-Trace", "abc"),
            ]
        )
        out = filter_allowlisted_proxy_response_headers(h)
        self.assertEqual(out.get("content-type"), "application/json")
        self.assertNotIn("set-cookie", {k.lower() for k in out})
        self.assertNotIn("location", {k.lower() for k in out})
        self.assertNotIn("x-internal-trace", {k.lower() for k in out})

    def test_openwebui_client_filter_matches_allowlist(self) -> None:
        h = httpx.Headers([("Content-Type", "text/event-stream"), ("Server", "uvicorn")])
        out = filter_openwebui_proxy_response_headers(h)
        self.assertEqual(out.get("content-type"), "text/event-stream")
        self.assertNotIn("server", {k.lower() for k in out})

    def test_profile_requires_auth(self) -> None:
        r = self.client.get("/me/profile")
        self.assertEqual(r.status_code, 401)

    def test_me_avatar_requires_auth(self) -> None:
        r = self.client.get("/me/avatar")
        self.assertEqual(r.status_code, 401)

    def test_memos_library_requires_auth(self) -> None:
        r = self.client.get("/me/library/stats")
        self.assertEqual(r.status_code, 401)

    def test_openwebui_workbench_session_requires_auth(self) -> None:
        r = self.client.get("/me/ai/workbench/session")
        self.assertEqual(r.status_code, 401)

    def test_vocechat_resource_requires_auth(self) -> None:
        r = self.client.get("/me/im/resources/group-avatar", params={"gid": 1})
        self.assertEqual(r.status_code, 401)

    def test_vocechat_resource_validation_error_not_500(self) -> None:
        self.client.post(
            "/auth/register",
            json={
                "username": "leakuser",
                "email": "leakuser@example.com",
                "password": "Secret123!",
            },
        )
        self.client.post(
            "/auth/login",
            json={"identifier": "leakuser", "password": "Secret123!"},
        )
        # Missing required query param -> 422
        r = self.client.get("/me/im/resources/group-avatar")
        self.assertEqual(r.status_code, 422)

    def test_admin_openwebui_routes_removed(self) -> None:
        self.client.post(
            "/auth/register",
            json={
                "username": "owuser",
                "email": "owuser@example.com",
                "password": "Secret123!",
            },
        )
        self.client.post(
            "/auth/login",
            json={"identifier": "owuser", "password": "Secret123!"},
        )
        r = self.client.get("/admin/openwebui/files")
        self.assertEqual(r.status_code, 404)

    def test_admin_vocechat_routes_removed(self) -> None:
        self.client.post(
            "/auth/register",
            json={
                "username": "nonadmin",
                "email": "nonadmin@example.com",
                "password": "Secret123!",
            },
        )
        self.client.post(
            "/auth/login",
            json={"identifier": "nonadmin", "password": "Secret123!"},
        )
        r = self.client.get("/admin/vocechat/system/version")
        self.assertEqual(r.status_code, 404)


    def test_profile_me_json_no_obvious_downstream_hosts(self) -> None:
        self.client.post(
            "/auth/register",
            json={
                "username": "jsonleak",
                "email": "jsonleak@example.com",
                "password": "Secret123!",
            },
        )
        self.client.post(
            "/auth/login",
            json={"identifier": "jsonleak", "password": "Secret123!"},
        )
        r = self.client.get("/me/profile")
        self.assertEqual(r.status_code, 200)
        text = r.text.lower()
        self.assertNotIn("openwebui", text)
        self.assertNotIn("127.0.0.1", text)
        self.assertNotIn("localhost:8080", text)


if __name__ == "__main__":
    unittest.main()
