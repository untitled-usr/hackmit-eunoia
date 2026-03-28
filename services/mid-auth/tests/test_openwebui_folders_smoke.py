import copy
import os
import time
import unittest
import uuid
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_folders.db"
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

DB_FILE = Path("/tmp/mid_auth_openwebui_folders.db")


class RecordingFoldersOWClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._folders: dict[str, dict[str, Any]] = {}
        self._fail_transport = False

    def close(self) -> None:
        return None

    def list_folders(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "parent_id": f.get("parent_id"),
                "meta": f.get("meta"),
                "is_expanded": f.get("is_expanded", False),
                "created_at": f["created_at"],
                "updated_at": f["updated_at"],
            }
            for f in self._folders.values()
        ]

    def get_folder(self, acting_uid: str, folder_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        row = self._folders.get(folder_id)
        if not row:
            raise OpenWebUIClientError("not found", http_status=404)
        return copy.deepcopy(row)

    def create_folder(self, acting_uid: str, body: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        fid = str(uuid.uuid4())
        now = int(time.time())
        row: dict[str, Any] = {
            "id": fid,
            "user_id": acting_uid,
            "name": body["name"],
            "parent_id": body.get("parent_id"),
            "data": body.get("data"),
            "meta": body.get("meta"),
            "items": None,
            "is_expanded": False,
            "created_at": now,
            "updated_at": now,
        }
        self._folders[fid] = row
        return copy.deepcopy(row)

    def update_folder(
        self, acting_uid: str, folder_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        row = self._folders.get(folder_id)
        if not row:
            raise OpenWebUIClientError("not found", http_status=404)
        if "name" in body and body["name"] is not None:
            row["name"] = body["name"]
        if "data" in body:
            row["data"] = body["data"]
        if "meta" in body:
            row["meta"] = body["meta"]
        row["updated_at"] = int(time.time())
        return copy.deepcopy(row)

    def delete_folder(
        self, acting_uid: str, folder_id: str, *, delete_contents: bool = True
    ) -> None:
        self.actings.append(acting_uid)
        if folder_id not in self._folders:
            raise OpenWebUIClientError("not found", http_status=404)
        del self._folders[folder_id]


class OpenWebUIFoldersSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = RecordingFoldersOWClient()

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
                "username": "folduser",
                "email": "folduser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "folduser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_create_get_patch_delete_flow(self) -> None:
        r = self.client.get("/me/ai/workbench/folders")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

        c = self.client.post("/me/ai/workbench/folders", json={"name": "Alpha"})
        self.assertEqual(c.status_code, 201)
        body = c.json()
        fid = body["id"]
        self.assertEqual(body["name"], "Alpha")

        g = self.client.get(f"/me/ai/workbench/folders/{fid}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["name"], "Alpha")

        p = self.client.patch(
            f"/me/ai/workbench/folders/{fid}",
            json={"name": "Beta"},
        )
        self.assertEqual(p.status_code, 200)
        self.assertEqual(p.json()["name"], "Beta")

        d = self.client.delete(f"/me/ai/workbench/folders/{fid}")
        self.assertEqual(d.status_code, 204)
        self.assertEqual(d.content, b"")

        again = self.client.get("/me/ai/workbench/folders")
        self.assertEqual(again.json(), [])

    def test_patch_empty_body_422(self) -> None:
        c = self.client.post("/me/ai/workbench/folders", json={"name": "x"})
        fid = c.json()["id"]
        r = self.client.patch(f"/me/ai/workbench/folders/{fid}", json={})
        self.assertEqual(r.status_code, 422)

    def test_no_openwebui_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/folders")
        self.assertEqual(r.status_code, 404)

    def test_openwebui_transport_maps_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/workbench/folders")
        self.assertEqual(r.status_code, 503)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/workbench/folders")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_me_openwebui_folders_not_routed(self) -> None:
        r = self.client.post("/me/openwebui/folders", json={"name": "nope"})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
