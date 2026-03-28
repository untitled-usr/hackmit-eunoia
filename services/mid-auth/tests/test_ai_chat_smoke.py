import copy
import os
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_ai_chat_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"
os.environ["MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID"] = "test-model"

from fastapi.testclient import TestClient

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.openwebui_client import OpenWebUIClientError
from app.main import app
from app.models.user_app_mappings import UserAppMapping

DB_FILE = Path("/tmp/mid_auth_ai_chat_smoke.db")


class RecordingOpenWebUIClient:
    """Minimal OpenWebUI stub for module-07 routes."""

    def __init__(self) -> None:
        self.actings: list[str] = []
        self.completions: list[dict[str, Any]] = []
        self._chats: dict[str, dict[str, Any]] = {}
        self._fail_transport = False
        self._http_error_status: int | None = None

    def close(self) -> None:
        pass

    def register_public(self) -> tuple[str, str]:
        raise NotImplementedError

    def delete_user_best_effort(self, user_id: str) -> None:
        return None

    def list_chats(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return [
            {
                "id": c["id"],
                "title": c["title"],
                "updated_at": c["updated_at"],
                "created_at": c["created_at"],
            }
            for c in self._chats.values()
        ]

    def get_chat(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        row = self._chats.get(chat_id)
        if not row:
            raise OpenWebUIClientError("not found", http_status=404)
        return copy.deepcopy(row)

    def create_chat(self, acting_uid: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        cid = f"c{len(self._chats) + 1}"
        now = int(time.time())
        row: dict[str, Any] = {
            "id": cid,
            "user_id": acting_uid,
            "title": chat.get("title", "New Chat"),
            "chat": copy.deepcopy(chat),
            "updated_at": now,
            "created_at": now,
            "share_id": None,
            "archived": False,
            "pinned": False,
            "meta": {},
            "folder_id": None,
        }
        self._chats[cid] = row
        return copy.deepcopy(row)

    def update_chat(
        self, acting_uid: str, chat_id: str, *, chat: dict[str, Any]
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        if self._http_error_status is not None:
            raise OpenWebUIClientError(
                "forced http error", http_status=self._http_error_status
            )
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        row = self._chats.get(chat_id)
        if not row:
            raise OpenWebUIClientError("not found", http_status=404)
        inner = row.get("chat") if isinstance(row.get("chat"), dict) else {}
        row["chat"] = {**inner, **chat}
        if "title" in chat:
            row["title"] = chat["title"]
        row["updated_at"] = int(time.time())
        return copy.deepcopy(row)

    def delete_chat(self, acting_uid: str, chat_id: str) -> bool:
        self.actings.append(acting_uid)
        if self._http_error_status is not None:
            raise OpenWebUIClientError(
                "forced http error", http_status=self._http_error_status
            )
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        if chat_id not in self._chats:
            raise OpenWebUIClientError("not found", http_status=404)
        del self._chats[chat_id]
        return True

    def chat_completion(self, acting_uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        self.completions.append(payload)
        last = payload.get("messages", [])[-1] if payload.get("messages") else {}
        u = last.get("content", "") if isinstance(last, dict) else ""
        return {"choices": [{"message": {"content": f"echo:{u}"}}]}


class AiChatSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = RecordingOpenWebUIClient()

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
                "username": "aiuser",
                "email": "aiuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "aiuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_chats_success(self) -> None:
        r = self.client.get("/me/ai/chats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["items"], [])
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_get_messages_success_empty_chat(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        self.assertEqual(c.status_code, 201)
        cid = c.json()["chat"]["id"]
        m = self.client.get(f"/me/ai/chats/{cid}/messages")
        self.assertEqual(m.status_code, 200)
        self.assertEqual(m.json()["items"], [])

    def test_post_create_empty_chat(self) -> None:
        r = self.client.post("/me/ai/chats", json={})
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("chat", body)
        self.assertNotIn("assistant_message", body)
        self.assertTrue(body["chat"]["id"])

    def test_post_create_with_first_body_returns_assistant(self) -> None:
        r = self.client.post(
            "/me/ai/chats",
            json={"body": "  hi  "},
        )
        self.assertEqual(r.status_code, 201)
        j = r.json()
        self.assertIn("assistant_message", j)
        self.assertEqual(j["assistant_message"]["role"], "assistant")
        self.assertEqual(j["assistant_message"]["body"], "echo:hi")
        msgs = self.client.get(
            f"/me/ai/chats/{j['chat']['id']}/messages"
        ).json()["items"]
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["body"], "hi")

    def test_append_message_success(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        a = self.client.post(
            f"/me/ai/chats/{cid}/messages",
            json={"body": "ping"},
        )
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json()["body"], "echo:ping")

    def test_no_openwebui_mapping_404_read_and_write(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()

        r = self.client.get("/me/ai/chats")
        self.assertEqual(r.status_code, 404)
        w = self.client.post("/me/ai/chats", json={"body": "x"})
        self.assertEqual(w.status_code, 404)

    def test_empty_body_400(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        r = self.client.post(f"/me/ai/chats/{cid}/messages", json={"body": "  "})
        self.assertEqual(r.status_code, 400)
        cr = self.client.post("/me/ai/chats", json={"body": " \t "})
        self.assertEqual(cr.status_code, 400)

    def test_openwebui_transport_maps_503(self) -> None:
        self.fake_ow._fail_transport = True
        r = self.client.get("/me/ai/chats")
        self.assertEqual(r.status_code, 503)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/chats")
        self.assertEqual(r.status_code, 401)
        raw.close()

    def test_append_invalid_body_422(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        r = self.client.post(f"/me/ai/chats/{cid}/messages", json={})
        self.assertEqual(r.status_code, 422)

    @patch("app.services.ai_chat_service.openwebui_acting_uid_header_value")
    def test_acting_uid_passed_to_client(self, mock_uid) -> None:
        mock_uid.return_value = "custom-acting"
        self.client.post("/me/ai/chats", json=None)
        mock_uid.assert_called()
        self.assertEqual(self.fake_ow.actings[-1], "custom-acting")

    def test_patch_chat_title_success(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        r = self.client.patch(
            f"/me/ai/chats/{cid}",
            json={"title": "  My Title  "},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["title"], "My Title")

    def test_delete_chat_success(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        d = self.client.delete(f"/me/ai/chats/{cid}")
        self.assertEqual(d.status_code, 204)
        self.assertEqual(d.content, b"")
        lst = self.client.get("/me/ai/chats").json()["items"]
        self.assertEqual(len(lst), 0)

    def test_no_mapping_patch_delete_404(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        p = self.client.patch(
            f"/me/ai/chats/{cid}",
            json={"title": "x"},
        )
        self.assertEqual(p.status_code, 404)
        dele = self.client.delete(f"/me/ai/chats/{cid}")
        self.assertEqual(dele.status_code, 404)

    def test_patch_empty_title_400(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        r = self.client.patch(
            f"/me/ai/chats/{cid}",
            json={"title": "   "},
        )
        self.assertEqual(r.status_code, 400)

    def test_patch_transport_503(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        self.fake_ow._fail_transport = True
        r = self.client.patch(
            f"/me/ai/chats/{cid}",
            json={"title": "ok"},
        )
        self.assertEqual(r.status_code, 503)

    def test_patch_unauthenticated_401(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        raw = TestClient(app)
        r = raw.patch(f"/me/ai/chats/{cid}", json={"title": "x"})
        self.assertEqual(r.status_code, 401)
        raw.close()

    @patch("app.services.ai_chat_service.openwebui_acting_uid_header_value")
    def test_patch_uses_acting_uid_for_client(self, mock_uid) -> None:
        mock_uid.return_value = "patch-acting"
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        self.client.patch(f"/me/ai/chats/{cid}", json={"title": "t"})
        mock_uid.assert_called()
        self.assertEqual(self.fake_ow.actings[-1], "patch-acting")

    def test_delete_twice_second_404(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        self.assertEqual(self.client.delete(f"/me/ai/chats/{cid}").status_code, 204)
        self.assertEqual(self.client.delete(f"/me/ai/chats/{cid}").status_code, 404)

    def test_patch_openwebui_403_maps_to_platform_403(self) -> None:
        c = self.client.post("/me/ai/chats", json=None)
        cid = c.json()["chat"]["id"]
        self.fake_ow._http_error_status = 403
        try:
            r = self.client.patch(
                f"/me/ai/chats/{cid}",
                json={"title": "x"},
            )
            self.assertEqual(r.status_code, 403)
        finally:
            self.fake_ow._http_error_status = None


if __name__ == "__main__":
    unittest.main()
