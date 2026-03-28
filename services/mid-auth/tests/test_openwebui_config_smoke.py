import os
import unittest
from pathlib import Path
from typing import Any

import httpx

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_config.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"

from fastapi.testclient import TestClient

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.openwebui_client import OpenWebUIClientError
from app.main import app
from app.models.user_app_mappings import UserAppMapping

DB_FILE = Path("/tmp/mid_auth_openwebui_config.db")


class FakeOpenWebUIClientForConfig:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self.calls: list[str] = []
        self.proxy_calls: list[tuple[str, str]] = []
        self._fail_transport = False
        self._banners: list[dict[str, Any]] = [
            {"id": "b1", "type": "info", "title": "Hi", "content": "x", "dismissible": True, "timestamp": 0}
        ]

    def close(self) -> None:
        pass

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
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        if acting_uid is not None:
            self.actings.append(acting_uid)
        self.proxy_calls.append((method.upper(), downstream_path))
        req = httpx.Request(method.upper(), f"http://openwebui.test{downstream_path}")
        if downstream_path == "/api/v1/configs/connections":
            return httpx.Response(
                200,
                json={"ENABLE_DIRECT_CONNECTIONS": True, "ENABLE_BASE_MODELS_CACHE": True},
                request=req,
            )
        if downstream_path == "/api/config":
            return httpx.Response(
                200,
                json={"name": "OW", "version": "0", "features": {"enable_direct_connections": True}},
                request=req,
            )
        if downstream_path == "/ollama/config":
            return httpx.Response(
                200,
                json={
                    "ENABLE_OLLAMA_API": False,
                    "OLLAMA_BASE_URLS": [""],
                    "OLLAMA_API_CONFIGS": {},
                },
                request=req,
            )
        return httpx.Response(404, json={"detail": "not found"}, request=req)

    def proxy_to_openwebui_stream(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected stream in config smoke tests")

    def get_configs_get_json(self, acting_uid: str, config_key: str) -> Any:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        self.calls.append(config_key)
        if config_key == "banners":
            return list(self._banners)
        raise OpenWebUIClientError("unexpected key", http_status=500)


class OpenWebUIConfigSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIClientForConfig()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "owcfg",
                "email": "owcfg@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owcfg", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_banners_success(self) -> None:
        r = self.client.get("/me/ai/workbench/config/banners")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIsInstance(j, list)
        self.assertEqual(len(j), 1)
        self.assertEqual(j[0]["id"], "b1")
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")
        self.assertEqual(self.fake_ow.calls, ["banners"])

    def test_workbench_safe_config_connections_still_404(self) -> None:
        r = self.client.get("/me/ai/workbench/config/connections")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"], "openwebui config not found")
        self.assertEqual(self.fake_ow.calls, [])

    def test_me_ai_configs_connections_proxies(self) -> None:
        r = self.client.get("/me/ai/configs/connections")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j.get("ENABLE_DIRECT_CONNECTIONS"))
        self.assertEqual(self.fake_ow.proxy_calls[-1], ("GET", "/api/v1/configs/connections"))

    def test_api_config_proxies(self) -> None:
        r = self.client.get("/api/config")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j.get("name"), "OW")
        self.assertEqual(self.fake_ow.proxy_calls[-1], ("GET", "/api/config"))

    def test_api_config_anonymous_without_session(self) -> None:
        """Open Web UI loads /api/config before login; must not require mid-auth session."""
        raw = TestClient(app)
        r = raw.get("/api/config")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j.get("name"), "OW")
        self.assertEqual(self.fake_ow.actings, [])
        raw.close()

    def test_ollama_requires_mid_auth_session(self) -> None:
        raw = TestClient(app)
        r = raw.get("/ollama/config")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_ollama_config_proxies(self) -> None:
        r = self.client.get("/ollama/config")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("OLLAMA_BASE_URLS", j)
        self.assertEqual(self.fake_ow.proxy_calls[-1], ("GET", "/ollama/config"))

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/config/banners")
        self.assertEqual(r.status_code, 404)
        r2 = self.client.get("/me/ai/configs/connections")
        self.assertEqual(r2.status_code, 404)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/workbench/config/banners")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_upstream_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/config/banners")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
