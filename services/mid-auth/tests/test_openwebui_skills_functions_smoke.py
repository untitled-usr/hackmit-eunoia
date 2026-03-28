import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_sf.db"
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

DB_FILE = Path("/tmp/mid_auth_openwebui_sf.db")


class FakeOpenWebUIClientSkillsFunctions:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False

    def close(self) -> None:
        pass

    def list_skills(self, acting_uid: str) -> Any:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return [{"id": "s1", "name": "Skill One"}]

    def get_skill(self, acting_uid: str, skill_id: str) -> Any:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return {"id": skill_id, "name": "One"}

    def list_functions(self, acting_uid: str) -> Any:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return [{"id": "f1", "name": "Fn One"}]

    def get_function(self, acting_uid: str, function_id: str) -> Any:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return {"id": function_id, "name": "Fn"}


class OpenWebUISkillsFunctionsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIClientSkillsFunctions()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "owsf",
                "email": "owsf@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owsf", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_list_skills(self) -> None:
        r = self.client.get("/me/ai/workbench/skills")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [{"id": "s1", "name": "Skill One"}])
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_get_skill(self) -> None:
        r = self.client.get("/me/ai/workbench/skills/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"id": "s1", "name": "One"})

    def test_list_functions(self) -> None:
        r = self.client.get("/me/ai/workbench/functions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [{"id": "f1", "name": "Fn One"}])

    def test_get_function(self) -> None:
        r = self.client.get("/me/ai/workbench/functions/f1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"id": "f1", "name": "Fn"})

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/skills")
        self.assertEqual(r.status_code, 404)

    def test_upstream_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/functions")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
