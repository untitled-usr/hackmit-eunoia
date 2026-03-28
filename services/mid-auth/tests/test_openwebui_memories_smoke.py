import copy
import os
import time
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_memories.db"
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

DB_FILE = Path("/tmp/mid_auth_openwebui_memories.db")


class RecordingMemoriesOpenWebUIClient:
    """Stub Open WebUI client with memories_* only (plus close)."""

    def __init__(self) -> None:
        self.actings: list[str] = []
        self._memories: dict[str, dict[str, Any]] = {}
        self._fail_transport = False
        self._query_404 = False

    def close(self) -> None:
        pass

    def memories_list(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return [copy.deepcopy(v) for v in self._memories.values()]

    def memories_add(self, acting_uid: str, *, content: str) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        mid = f"m{len(self._memories) + 1}"
        now = int(time.time())
        row: dict[str, Any] = {
            "id": mid,
            "user_id": acting_uid,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
        self._memories[mid] = row
        return copy.deepcopy(row)

    def memories_query(
        self, acting_uid: str, *, content: str, k: int | None
    ) -> dict[str, Any]:
        if self._query_404:
            raise OpenWebUIClientError("none", http_status=404)
        self.actings.append(acting_uid)
        rows = list(self._memories.values())
        if k is not None:
            rows = rows[:k]
        return {
            "ids": [[str(r["id"]) for r in rows]],
            "documents": [[str(r["content"]) for r in rows]],
            "distances": [[0.95 for _ in rows]],
        }

    def memories_reset(self, acting_uid: str) -> bool:
        self.actings.append(acting_uid)
        return True

    def memories_update(
        self, acting_uid: str, memory_id: str, *, content: str
    ) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        row = self._memories.get(memory_id)
        if not row:
            raise OpenWebUIClientError("nf", http_status=404)
        row["content"] = content
        row["updated_at"] = int(time.time())
        return copy.deepcopy(row)


class OpenWebUIMemoriesSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = RecordingMemoriesOpenWebUIClient()

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
                "username": "memuser",
                "email": "memuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "memuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_empty_then_add_and_list(self) -> None:
        r = self.client.get("/me/ai/workbench/memories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["items"], [])
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

        c = self.client.post(
            "/me/ai/workbench/memories",
            json={"body": "  hello memory  "},
        )
        self.assertEqual(c.status_code, 201)
        item = c.json()
        self.assertIn("id", item)
        self.assertEqual(item["body"], "hello memory")
        self.assertNotIn("user_id", item)
        self.assertNotIn("content", item)

        lst = self.client.get("/me/ai/workbench/memories").json()["items"]
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["body"], "hello memory")

    def test_query_returns_platform_hits(self) -> None:
        self.client.post("/me/ai/workbench/memories", json={"body": "alpha"})
        q = self.client.post(
            "/me/ai/workbench/memories/query",
            json={"body": "alpha", "limit": 3},
        )
        self.assertEqual(q.status_code, 200)
        hits = q.json()["items"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["body"], "alpha")
        self.assertIn("score", hits[0])
        self.assertNotIn("documents", q.json())

    def test_reset_ok(self) -> None:
        r = self.client.post("/me/ai/workbench/memories/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_patch_memory(self) -> None:
        mid = self.client.post(
            "/me/ai/workbench/memories",
            json={"body": "old"},
        ).json()["id"]
        p = self.client.patch(
            f"/me/ai/workbench/memories/{mid}",
            json={"body": "new text"},
        )
        self.assertEqual(p.status_code, 200)
        self.assertEqual(p.json()["body"], "new text")

    def test_patch_unknown_404(self) -> None:
        r = self.client.patch(
            "/me/ai/workbench/memories/nope",
            json={"body": "x"},
        )
        self.assertEqual(r.status_code, 404)

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        self.assertEqual(
            self.client.get("/me/ai/workbench/memories").status_code,
            404,
        )

    def test_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        self.assertEqual(
            self.client.get("/me/ai/workbench/memories").status_code,
            503,
        )

    def test_empty_body_400(self) -> None:
        self.assertEqual(
            self.client.post("/me/ai/workbench/memories", json={"body": "  "}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/me/ai/workbench/memories/query",
                json={"body": ""},
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
