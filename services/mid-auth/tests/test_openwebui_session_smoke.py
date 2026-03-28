import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_session.db"
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

DB_FILE = Path("/tmp/mid_auth_openwebui_session.db")


class FakeOpenWebUIClientForSession:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False
        self._session_payload: dict[str, Any] = {
            "token": "",
            "token_type": "ActingUid",
            "expires_at": None,
            "permissions": {"workspace": {"models": False}},
            "id": "ow-user-1",
            "name": "OW Name",
            "role": "user",
            "profile_image_url": "/api/v1/users/ow-user-1/profile/image",
            "bio": None,
            "gender": None,
            "date_of_birth": None,
            "status_emoji": None,
            "status_message": None,
            "status_expires_at": None,
        }

    def close(self) -> None:
        pass

    def get_session_user(self, acting_uid: str) -> dict[str, Any]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return dict(self._session_payload)


class OpenWebUISessionSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIClientForSession()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "owsess",
                "email": "owsess@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owsess", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_session_success(self) -> None:
        r = self.client.get("/me/ai/workbench/session")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["id"], "ow-user-1")
        self.assertEqual(j["name"], "OW Name")
        self.assertEqual(j["role"], "user")
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_openapi_excludes_me_openwebui_paths(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertNotIn("/me/openwebui/session", schema["paths"])

    def test_me_openwebui_session_not_routed(self) -> None:
        r = self.client.get("/me/openwebui/session")
        self.assertEqual(r.status_code, 404)

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/session")
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/workbench/session")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_upstream_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/session")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
