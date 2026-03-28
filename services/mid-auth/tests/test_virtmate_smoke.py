import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_virtmate_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"

from fastapi.testclient import TestClient

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import engine
from app.main import app

DB_FILE = Path("/tmp/mid_auth_virtmate_smoke.db")


class _FakeStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def iter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class FakeOpenWebUIClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self.chats: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        pass

    def create_chat(self, acting_uid: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        cid = "chat-1"
        self.chats[cid] = {"id": cid, "chat": chat, "title": "New Chat", "updated_at": 0, "created_at": 0}
        return {"id": cid, "title": "New Chat", "updated_at": 0, "created_at": 0}

    def get_chat(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        return self.chats[chat_id]

    def update_chat(self, acting_uid: str, chat_id: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        self.chats[chat_id] = {"id": chat_id, "chat": chat, "title": chat.get("title") or "New Chat", "updated_at": 0, "created_at": 0}
        return {"id": chat_id, "title": chat.get("title") or "New Chat", "updated_at": 0, "created_at": 0}

    def chat_completion(self, acting_uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.actings.append(acting_uid)
        _ = payload
        return {"choices": [{"message": {"content": "hello from ai"}}]}

    def proxy_to_openwebui_stream(
        self,
        acting_uid: str | None,
        *,
        method: str,
        downstream_path: str,
        params: list[tuple[str, str]] | dict[str, Any] | None = None,
        content: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        _ = method, downstream_path, params, content, extra_headers
        self.actings.append(acting_uid or "")
        return _FakeStream(
            [
                b'data: {"choices":[{"delta":{"content":"hello "}}]}\n',
                b'data: {"choices":[{"delta":{"content":"stream"}}]}\n',
                b"data: [DONE]\n",
            ]
        )


class VirtmateSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIClient()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "virtmate",
                "email": "virtmate@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "virtmate", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_settings_and_global(self) -> None:
        r = self.client.get("/me/virtmate/session/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn("tts_engine", r.json())

        r2 = self.client.post(
            "/me/virtmate/session/settings",
            json={"session_id": "default", "username": "alice", "mate_name": "bob"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["username"], "alice")

        g = self.client.get("/me/virtmate/config/global")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["openwebui"]["user_id_header"], "X-Acting-Uid")

    def test_chat_send_uses_current_user_mapping(self) -> None:
        r = self.client.post(
            "/me/virtmate/chat/send",
            json={
                "session_id": "default",
                "text": "hi",
                "stream": False,
                "with_tts": False,
                "model": "test-model",
            },
        )
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["assistant"]["content"], "hello from ai")
        self.assertTrue(self.fake_ow.actings)
        self.assertEqual(self.fake_ow.actings[0], "stub-openwebui")

    def test_tts_playback_and_mouth_y(self) -> None:
        r = self.client.post(
            "/me/virtmate/tts/playback",
            json={"session_id": "s1", "is_playing": True, "mouth_y": 0.6},
        )
        self.assertEqual(r.status_code, 200)
        y = self.client.get("/me/virtmate/scene/mouth_y", params={"session_id": "s1"})
        self.assertEqual(y.status_code, 200)
        self.assertGreater(float(y.json()["y"]), 0.0)


if __name__ == "__main__":
    unittest.main()

