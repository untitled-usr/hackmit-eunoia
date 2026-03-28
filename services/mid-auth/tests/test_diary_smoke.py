import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_diary_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_MEMOS_BASE_URL"] = "http://memos.test"

from fastapi.testclient import TestClient

from app.api.deps.memos_client_dep import get_memos_client
from app.db.base import Base
from app.db.session import engine
from app.integrations.memos_client import MemosClientError
from app.main import app

DB_FILE = Path("/tmp/mid_auth_diary_smoke.db")


class DiaryMemosStub:
    def __init__(self) -> None:
        self._memos: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def close(self) -> None:
        pass

    def create_memo(
        self,
        acting_uid: str,
        *,
        content: str,
        visibility: str = "PRIVATE",
        location: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        uid = f"m{self._counter}"
        row = {
            "name": f"memos/{uid}",
            "creator": "users/1",
            "content": content,
            "visibility": visibility,
            "state": "NORMAL",
            "location": location or {},
            "tags": ["diary"],
            "createTime": "2024-06-01T12:00:00Z",
            "updateTime": "2024-06-01T12:00:00Z",
        }
        self._memos[uid] = row
        return dict(row)

    def get_memo(self, acting_uid: str, memo_uid: str) -> dict[str, Any]:
        uid = memo_uid.removeprefix("memos/")
        row = self._memos.get(uid)
        if row is None:
            raise MemosClientError("nf", http_status=404)
        return dict(row)

    def update_memo(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        uid = memo_uid.removeprefix("memos/")
        row = self._memos.get(uid)
        if row is None:
            raise MemosClientError("nf", http_status=404)
        if "content" in update_mask and "content" in body:
            row["content"] = body["content"]
        if "location" in update_mask and "location" in body:
            row["location"] = body["location"]
        if "state" in update_mask and "state" in body:
            row["state"] = body["state"]
        row["updateTime"] = "2024-06-02T12:00:00Z"
        self._memos[uid] = row
        return dict(row)

    def list_memos(
        self,
        acting_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        filter_expr: str | None = None,
        state: str | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        items = list(self._memos.values())
        if state:
            items = [m for m in items if str(m.get("state")) == state]
        return {"memos": [dict(x) for x in items], "nextPageToken": ""}


class DiarySmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_memos = DiaryMemosStub()

        def _dep():
            yield self.fake_memos

        app.dependency_overrides[get_memos_client] = _dep
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
                "username": "diaryuser",
                "email": "diaryuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "diaryuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_diary_crud_and_reorder(self) -> None:
        create = self.client.post(
            "/me/diary/entries",
            json={
                "title": "Day 1",
                "content": "hello diary",
                "keywords": ["mood", "today"],
                "status": "normal",
                "order": 2,
            },
        )
        self.assertEqual(create.status_code, 201)
        eid = create.json()["id"]
        self.assertEqual(create.json()["title"], "Day 1")
        self.assertEqual(create.json()["status"], "normal")

        patch = self.client.patch(
            f"/me/diary/entries/{eid}",
            json={"status": "digested", "order": 9},
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["status"], "digested")
        self.assertEqual(patch.json()["order"], 9)

        second = self.client.post(
            "/me/diary/entries",
            json={"title": "Day 2", "content": "entry2", "order": 1},
        )
        self.assertEqual(second.status_code, 201)
        eid2 = second.json()["id"]

        reorder = self.client.patch(
            "/me/diary/entries/reorder",
            json={"entries": [{"id": eid, "order": 1}, {"id": eid2, "order": 2}]},
        )
        self.assertEqual(reorder.status_code, 200)
        self.assertEqual(len(reorder.json()["items"]), 2)
        self.assertEqual(reorder.json()["items"][0]["id"], eid)

        listed = self.client.get("/me/diary/entries")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()["items"]), 2)

    def test_diary_patch_not_found(self) -> None:
        patch = self.client.patch("/me/diary/entries/not-exist", json={"status": "normal"})
        self.assertEqual(patch.status_code, 404)


if __name__ == "__main__":
    unittest.main()

