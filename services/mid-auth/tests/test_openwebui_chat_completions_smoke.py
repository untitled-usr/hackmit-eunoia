"""Smoke: POST /me/ai/workbench/chat/completions (stream + non-stream; mocked downstream)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_openwebui_chat_completion.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"

from fastapi.testclient import TestClient

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import engine
from app.integrations.openwebui_client import OpenWebUIClientError
from app.main import app
from app.services.openwebui_chat_stream_service import OpenWebUIChatStreamError

DB_FILE = Path("/tmp/mid_auth_openwebui_chat_completion.db")


class _FakeStreamSession:
    def response_content_type(self) -> str:
        return "text/event-stream"

    async def stream_bytes(self):
        yield b"data: {\"x\":1}\n\n"


class FakeOWChatCompletion:
    def __init__(self) -> None:
        self.completions: list[dict[str, Any]] = []

    def close(self) -> None:
        pass

    def chat_completion(self, acting_uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.completions.append(payload)
        return {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "model": payload.get("model", ""),
        }


class OpenWebUIChatCompletionsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOWChatCompletion()

        def _dep():
            yield self.fake_ow

        app.dependency_overrides[get_openwebui_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "owccuser",
                "email": "owccuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owccuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_stream_returns_event_stream_when_session_mocked(self) -> None:
        fake = _FakeStreamSession()
        with patch(
            "app.api.routers.openwebui_me.OpenWebUIChatCompletionsStreamSession.start",
            new_callable=AsyncMock,
            return_value=fake,
        ) as mock_start:
            with self.client.stream(
                "POST",
                "/me/ai/workbench/chat/completions",
                json={"model": "m1", "messages": [], "stream": True},
            ) as r:
                self.assertEqual(r.status_code, 200)
                self.assertIn("text/event-stream", r.headers.get("content-type", ""))
                body = r.read()
        self.assertIn(b"data:", body)
        mock_start.assert_called_once()

    def test_stream_upstream_error_json(self) -> None:
        with patch(
            "app.api.routers.openwebui_me.OpenWebUIChatCompletionsStreamSession.start",
            new_callable=AsyncMock,
            side_effect=OpenWebUIChatStreamError(503, "openwebui upstream unavailable"),
        ):
            r = self.client.post(
                "/me/ai/workbench/chat/completions",
                json={"model": "m1", "messages": [], "stream": True},
            )
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"], "openwebui upstream unavailable")

    def test_non_stream_returns_json(self) -> None:
        r = self.client.post(
            "/me/ai/workbench/chat/completions",
            json={"model": "m1", "messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["choices"][0]["message"]["content"], "hello")
        self.assertEqual(self.fake_ow.completions[-1]["model"], "m1")

    def test_non_stream_upstream_error_mapped(self) -> None:
        def _boom(_acting: str, _payload: dict[str, Any]) -> dict[str, Any]:
            raise OpenWebUIClientError("nope", http_status=401)

        self.fake_ow.chat_completion = _boom  # type: ignore[method-assign]
        r = self.client.post(
            "/me/ai/workbench/chat/completions",
            json={"model": "m1", "messages": []},
        )
        self.assertEqual(r.status_code, 404)
        self.assertIn("not found", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
