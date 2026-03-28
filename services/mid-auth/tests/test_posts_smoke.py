import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_posts_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_MEMOS_BASE_URL"] = "http://memos.test"

from fastapi.testclient import TestClient

from app.api.deps.memos_client_dep import get_memos_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.memos_client import MemosClientError
from app.main import app
from app.models.user_app_mappings import UserAppMapping

DB_FILE = Path("/tmp/mid_auth_posts_smoke.db")


class RecordingMemosClient:
    """In-memory Memos stub; records acting Uids and list filters."""

    def __init__(self) -> None:
        self.actings: list[str] = []
        self.list_calls: list[dict[str, Any]] = []
        self._memos: dict[str, dict[str, Any]] = {}
        self._fail_transport = False
        self._counter = 0

    def close(self) -> None:
        pass

    def create_memo(
        self, acting_uid: str, *, content: str, visibility: str = "PRIVATE"
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        self._counter += 1
        uid = f"id{self._counter}"
        row = {
            "name": f"memos/{uid}",
            "content": content,
            "visibility": visibility,
            "createTime": "2024-06-01T12:00:00Z",
            "updateTime": "2024-06-01T12:00:00Z",
        }
        self._memos[uid] = row
        return dict(row)

    def list_memos(
        self,
        acting_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        if self._fail_transport:
            raise MemosClientError("boom", transport=True)
        self.actings.append(acting_uid)
        self.list_calls.append(
            {
                "page_size": page_size,
                "page_token": page_token,
                "filter_expr": filter_expr,
            }
        )
        return {
            "memos": list(self._memos.values()),
            "nextPageToken": "",
        }

    def get_memo(self, acting_uid: str, memo_uid: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        m = self._memos.get(uid)
        if not m:
            raise MemosClientError("nf", http_status=404)
        return dict(m)

    def update_memo_content(
        self, acting_uid: str, memo_uid: str, *, content: str
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        m = self._memos.get(uid)
        if not m:
            raise MemosClientError("nf", http_status=404)
        updated = {**m, "content": content, "updateTime": "2024-06-02T12:00:00Z"}
        self._memos[uid] = updated
        return dict(updated)

    def delete_memo(self, acting_uid: str, memo_uid: str) -> None:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        if uid not in self._memos:
            raise MemosClientError("nf", http_status=404)
        del self._memos[uid]

    def list_memo_reactions(
        self,
        acting_uid: str,
        memo_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        if uid not in self._memos:
            raise MemosClientError("nf", http_status=404)
        return {
            "reactions": [
                {
                    "name": f"memos/{uid}/reactions/r1",
                    "reactionType": "👍",
                    "creator": "users/1",
                    "createTime": "2024-06-01T12:00:00Z",
                }
            ],
            "nextPageToken": "t",
            "totalSize": 1,
        }

    def upsert_memo_reaction(
        self, acting_uid: str, memo_uid: str, *, body: dict[str, Any]
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        if uid not in self._memos:
            raise MemosClientError("nf", http_status=404)
        return {
            "name": f"memos/{uid}/reactions/r2",
            "reactionType": "❤️",
            "creator": "users/1",
            "createTime": "2024-06-02T12:00:00Z",
        }

    def delete_memo_reaction(
        self, acting_uid: str, memo_uid: str, reaction_id: str
    ) -> None:
        self.actings.append(acting_uid)
        uid = memo_uid.removeprefix("memos/")
        if uid not in self._memos:
            raise MemosClientError("nf", http_status=404)


class PostsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_memos = RecordingMemosClient()

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
                "username": "postuser",
                "email": "postuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "postuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_post_crud_success_and_acting_uid(self) -> None:
        c = self.client.post("/me/posts", json={"body": "  hello  "})
        self.assertEqual(c.status_code, 201)
        created = c.json()
        self.assertEqual(created["body"], "hello")
        self.assertEqual(created["visibility"], "private")
        self.assertIn("id", created)
        self.assertEqual(self.fake_memos.actings[-1], "1")

        lid = created["id"]

        lst = self.client.get("/me/posts")
        self.assertEqual(lst.status_code, 200)
        body = lst.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["id"], lid)
        self.assertEqual(self.fake_memos.actings[-1], "1")
        self.assertTrue(self.fake_memos.list_calls)
        self.assertEqual(self.fake_memos.list_calls[-1]["filter_expr"], "creator_id == 1")

        one = self.client.get(f"/me/posts/{lid}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["body"], "hello")
        self.assertEqual(self.fake_memos.actings[-1], "1")

        pat = self.client.patch(f"/me/posts/{lid}", json={"body": "  bye  "})
        self.assertEqual(pat.status_code, 200)
        self.assertEqual(pat.json()["body"], "bye")

        dele = self.client.delete(f"/me/posts/{lid}")
        self.assertEqual(dele.status_code, 204)

    def test_post_reactions_list_upsert_delete_and_path_validation(self) -> None:
        c = self.client.post("/me/posts", json={"body": "rx"})
        self.assertEqual(c.status_code, 201)
        lid = c.json()["id"]

        lr = self.client.get(f"/me/posts/{lid}/reactions?pageSize=10")
        self.assertEqual(lr.status_code, 200)
        data = lr.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["id"], "r1")
        self.assertEqual(data["items"][0]["reaction_type"], "👍")
        self.assertEqual(data["next_page_token"], "t")
        self.assertEqual(data["total_size"], 1)

        up = self.client.post(
            f"/me/posts/{lid}/reactions",
            json={"name": f"memos/{lid}", "reaction": {"reactionType": "❤️"}},
        )
        self.assertEqual(up.status_code, 200)
        self.assertEqual(up.json()["id"], "r2")
        self.assertEqual(up.json()["reaction_type"], "❤️")

        dr = self.client.delete(f"/me/posts/{lid}/reactions/r2")
        self.assertEqual(dr.status_code, 204)

        nf = self.client.get("/me/posts/unknown-memo-999/reactions")
        self.assertEqual(nf.status_code, 404)

    def test_no_memos_mapping_returns_404_read_and_write(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "memos"
            ).delete()
            db.commit()

        r = self.client.get("/me/posts")
        self.assertEqual(r.status_code, 404)

        w = self.client.post("/me/posts", json={"body": "x"})
        self.assertEqual(w.status_code, 404)

    def test_empty_body_400(self) -> None:
        r = self.client.post("/me/posts", json={"body": "   "})
        self.assertEqual(r.status_code, 400)

    def test_memos_transport_maps_503(self) -> None:
        self.fake_memos._fail_transport = True
        r = self.client.get("/me/posts")
        self.assertEqual(r.status_code, 503)

    @patch("app.services.posts_service.memos_acting_uid_header_value")
    def test_service_uses_mapping_for_acting_uid(self, mock_hdr) -> None:
        mock_hdr.return_value = "99"
        p = self.client.post("/me/posts", json={"body": "z"})
        self.assertEqual(p.status_code, 201)
        mock_hdr.assert_called()
        self.assertEqual(self.fake_memos.actings[-1], "99")


if __name__ == "__main__":
    unittest.main()
