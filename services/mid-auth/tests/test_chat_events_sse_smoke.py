"""Smoke tests for ``GET /me/im/events`` (VoceChat SSE proxy).

**Integration strategy**

- **Happy path:** Patch ``VoceChatSseSession.start`` to return a fake session whose
  ``stream_bytes`` yields synthetic SSE bytes; assert ``text/event-stream`` and body.
- **Upstream errors:** Patch ``start`` to raise ``VoceChatEventStreamError`` and assert
  JSON error response **before** any streaming body (session is opened in the handler
  prior to ``StreamingResponse``).
- **Redis lease (optional):** With ``MID_AUTH_VOCECHAT_SSE_REDIS_URL`` set, patch
  ``redis.Redis.from_url`` so ``set(..., nx=True)`` returns ``False`` and expect **409**.

End-to-end tests against a real VoceChat and Redis belong in a separate deployment
check / CI job; this file keeps CI hermetic.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_sse_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_VOCECHAT_BASE_URL"] = "http://vocechat.test/api"

from fastapi.testclient import TestClient

from app.api.deps.vocechat_client_dep import get_vocechat_client
from app.db.base import Base
from app.db.session import engine
from app.integrations.vocechat_client import VoceChatClient, build_vocechat_user_events_url
from app.main import app
from app.services.vocechat_events_proxy import VoceChatEventStreamError

DB_FILE = Path("/tmp/mid_auth_sse_smoke.db")


class _FakeSseSession:
    def __init__(self, payload: bytes = b"data: {}\n\n") -> None:
        self._payload = payload

    async def stream_bytes(self):
        yield self._payload


class ChatEventsSseSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        class _MinimalVc:
            def close(self) -> None:
                pass

        def _dep():
            yield _MinimalVc()

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "sseuser",
                "email": "sseuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "sseuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_build_user_events_url_encodes_query(self) -> None:
        u = build_vocechat_user_events_url(
            "http://vocechat.test/api",
            after_mid=7,
            users_version=3,
        )
        self.assertTrue(
            u.startswith("http://vocechat.test/api/user/events?"), u
        )
        self.assertIn("after_mid=7", u)
        self.assertIn("users_version=3", u)

    def test_vocechat_client_build_user_events_url(self) -> None:
        vc = VoceChatClient(
            "http://vc.example/api",
            5.0,
            "X-Acting-Uid",
            None,
        )
        try:
            self.assertEqual(
                vc.build_user_events_url(after_mid=1),
                "http://vc.example/api/user/events?after_mid=1",
            )
        finally:
            vc.close()

    def test_sse_streams_when_session_start_mocked(self) -> None:
        fake = _FakeSseSession()
        with patch(
            "app.api.routers.conversations.VoceChatSseSession.start",
            new_callable=AsyncMock,
            return_value=fake,
        ) as mock_start:
            with self.client.stream(
                "GET",
                "/me/im/events",
                params={"after_mid": 9},
            ) as r:
                self.assertEqual(r.status_code, 200)
                self.assertIn("text/event-stream", r.headers.get("content-type", ""))
                body = r.read()
        self.assertIn(b"data:", body)
        mock_start.assert_called_once()

    def test_sse_upstream_error_returns_json_not_200_stream(self) -> None:
        with patch(
            "app.api.routers.conversations.VoceChatSseSession.start",
            new_callable=AsyncMock,
            side_effect=VoceChatEventStreamError(
                401, "chat authentication failed"
            ),
        ):
            r = self.client.get("/me/im/events")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "chat authentication failed")

    def test_sse_redis_lease_conflict_409(self) -> None:
        mock_r = MagicMock()
        mock_r.set.return_value = False

        with patch.dict(
            os.environ,
            {"MID_AUTH_VOCECHAT_SSE_REDIS_URL": "redis://127.0.0.1:6379/0"},
        ):
            with patch(
                "app.services.vocechat_events_proxy.redis.Redis.from_url",
                return_value=mock_r,
            ):
                r = self.client.get("/me/im/events")
        self.assertEqual(r.status_code, 409)
        self.assertIn("detail", r.json())
        mock_r.set.assert_called_once()
        mock_r.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
