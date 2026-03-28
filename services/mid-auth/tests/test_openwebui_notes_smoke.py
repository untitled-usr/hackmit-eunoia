import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_notes.db"
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

DB_FILE = Path("/tmp/mid_auth_openwebui_notes.db")


class FakeOpenWebUIClientForNotes:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self.pages: list[int | None] = []
        self._fail_transport = False

    def close(self) -> None:
        pass

    def list_notes(self, acting_uid: str, *, page: int | None = None) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        self.pages.append(page)
        return [
            {
                "id": "n1",
                "title": "T1",
                "data": {"content": {"md": "hi"}},
                "updated_at": 1,
                "created_at": 1,
            }
        ]

    def get_note(self, acting_uid: str, note_id: str) -> dict[str, Any]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return {
            "id": note_id,
            "title": "Detail",
            "write_access": False,
            "user_id": "u1",
            "data": {},
        }


class OpenWebUINotesSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIClientForNotes()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "ownotes",
                "email": "ownotes@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "ownotes", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_list_notes_success(self) -> None:
        r = self.client.get("/me/ai/workbench/notes")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(len(j), 1)
        self.assertEqual(j[0]["id"], "n1")
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")
        self.assertIsNone(self.fake_ow.pages[-1])

    def test_list_notes_with_page(self) -> None:
        r = self.client.get("/me/ai/workbench/notes?page=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.fake_ow.pages[-1], 2)

    def test_get_note_success(self) -> None:
        r = self.client.get("/me/ai/workbench/notes/n1")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["id"], "n1")
        self.assertEqual(j["title"], "Detail")

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/notes")
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/workbench/notes")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_upstream_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/notes")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
