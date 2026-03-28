import os
import unittest
from typing import Any
from urllib.parse import unquote

from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_prompts_smoke.db"
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


class FakePromptsOpenWebUIClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._prompts: dict[str, dict[str, Any]] = {
            "p1": {
                "id": "p1",
                "command": "hello",
                "name": "Hello",
                "content": "body",
                "user_id": "stub-openwebui",
                "write_access": True,
            }
        }
        self._fail_transport = False
        self._http_error_status: int | None = None

    def close(self) -> None:
        return None

    def list_prompts(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return list(self._prompts.values())

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
        self.actings.append(acting_uid)
        return {"items": list(self._prompts.values()), "total": len(self._prompts)}

    def get_prompt_by_command(self, acting_uid: str, command: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        raw = unquote(command)
        for p in self._prompts.values():
            if p.get("command") == raw:
                return dict(p)
        raise OpenWebUIClientError("nf", http_status=404)

    def get_prompt_by_id(self, acting_uid: str, prompt_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        p = self._prompts.get(prompt_id)
        if not p:
            raise OpenWebUIClientError("nf", http_status=404)
        return dict(p)

    def update_prompt(
        self, acting_uid: str, prompt_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        if self._http_error_status is not None:
            raise OpenWebUIClientError(
                "x", http_status=self._http_error_status
            )
        self.actings.append(acting_uid)
        row = self._prompts.get(prompt_id)
        if not row:
            raise OpenWebUIClientError("nf", http_status=404)
        merged = {**row, **body, "id": prompt_id}
        self._prompts[prompt_id] = merged
        return dict(merged)

    def delete_prompt(self, acting_uid: str, prompt_id: str) -> bool:
        self.actings.append(acting_uid)
        if prompt_id not in self._prompts:
            raise OpenWebUIClientError("nf", http_status=404)
        del self._prompts[prompt_id]
        return True


class OpenWebUIPromptsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakePromptsOpenWebUIClient()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        self._register_and_login()

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _register_and_login(self) -> None:
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "puser",
                "email": "puser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "puser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_prompts_success(self) -> None:
        r = self.client.get("/me/ai/workbench/prompts")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["command"], "hello")
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_list_page(self) -> None:
        r = self.client.get("/me/ai/workbench/prompts/list?page=1")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["total"], 1)
        self.assertEqual(len(j["items"]), 1)

    def test_get_by_command(self) -> None:
        r = self.client.get("/me/ai/workbench/prompts/by-command/hello")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "p1")

    def test_get_by_id(self) -> None:
        r = self.client.get("/me/ai/workbench/prompts/p1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Hello")

    def test_patch_and_delete(self) -> None:
        p = self.client.patch(
            "/me/ai/workbench/prompts/p1",
            json={"command": "hello", "name": "Hi", "content": "body"},
        )
        self.assertEqual(p.status_code, 200)
        self.assertEqual(p.json()["name"], "Hi")
        d = self.client.delete("/me/ai/workbench/prompts/p1")
        self.assertEqual(d.status_code, 204)
        self.assertEqual(d.content, b"")
        g = self.client.get("/me/ai/workbench/prompts/p1")
        self.assertEqual(g.status_code, 404)

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/prompts")
        self.assertEqual(r.status_code, 404)

    def test_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/prompts")
        self.assertEqual(r.status_code, 503)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        self.assertEqual(raw.get("/me/ai/workbench/prompts").status_code, 401)
        raw.close()

    @patch("app.services.openwebui_prompts_service.openwebui_acting_uid_header_value")
    def test_acting_uid_passed(self, mock_uid) -> None:
        mock_uid.return_value = "acting-z"
        self.client.get("/me/ai/workbench/prompts")
        mock_uid.assert_called()
        self.assertEqual(self.fake_ow.actings[-1], "acting-z")

    def test_patch_upstream_403(self) -> None:
        self.fake_ow._http_error_status = 403
        try:
            r = self.client.patch(
                "/me/ai/workbench/prompts/p1",
                json={"command": "hello", "name": "x", "content": "c"},
            )
            self.assertEqual(r.status_code, 403)
        finally:
            self.fake_ow._http_error_status = None


if __name__ == "__main__":
    unittest.main()
