import os
import unittest
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_tools_smoke.db"
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


class FakeToolsOpenWebUIClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False
        self._tools: list[dict[str, Any]] = [
            {"id": "t1", "name": "one", "write_access": True},
        ]
        self._valves: dict[str, dict[str, Any] | None] = {"t1": {"k": "v"}}

    def close(self) -> None:
        pass

    def list_tools(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return list(self._tools)

    def get_tool(self, acting_uid: str, tool_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        for t in self._tools:
            if t.get("id") == tool_id:
                return dict(t)
        raise OpenWebUIClientError("missing", http_status=404)

    def get_tool_valves(self, acting_uid: str, tool_id: str) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        if tool_id == "none":
            return None
        if tool_id not in self._valves:
            raise OpenWebUIClientError("missing", http_status=404)
        return self._valves.get(tool_id)

    def update_tool_valves(
        self, acting_uid: str, tool_id: str, body: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        if tool_id == "missing":
            raise OpenWebUIClientError("nope", http_status=404)
        merged = {**(self._valves.get(tool_id) or {}), **body}
        self._valves[tool_id] = merged
        return merged


class OpenWebUIToolsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeToolsOpenWebUIClient()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "owtools",
                "email": "owtools@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owtools", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_list_tools_success(self) -> None:
        r = self.client.get("/me/ai/workbench/tools")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_get_tool_detail(self) -> None:
        r = self.client.get("/me/ai/workbench/tools/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "t1")

    def test_get_valves(self) -> None:
        r = self.client.get("/me/ai/workbench/tools/t1/valves")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"k": "v"})

    def test_get_valves_null(self) -> None:
        r = self.client.get("/me/ai/workbench/tools/none/valves")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json())

    def test_patch_valves(self) -> None:
        r = self.client.patch(
            "/me/ai/workbench/tools/t1/valves",
            json={"k": "new"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"k": "new"})

    def test_no_openwebui_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/tools")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"], "openwebui mapping not found")

    def test_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/tools")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"], "openwebui upstream unavailable")


if __name__ == "__main__":
    unittest.main()
