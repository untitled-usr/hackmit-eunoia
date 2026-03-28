"""Smoke tests for VoceChat resource proxies (file, archive, open-graphic)."""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_chat_resources_smoke.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_VOCECHAT_BASE_URL"] = "http://vocechat.test/api"

from fastapi.testclient import TestClient

from app.api.deps.vocechat_client_dep import get_vocechat_client
from app.db.base import Base
from app.db.session import engine
from app.integrations.vocechat_client import VoceChatClientError
from app.main import app

from tests.test_chat_smoke import RecordingVoceChatClient

DB_FILE = Path("/tmp/mid_auth_chat_resources_smoke.db")


class _FakeStreamResponse:
    """Minimal httpx-like streaming response for ``_proxy_httpx_stream``."""

    def __init__(
        self,
        status_code: int,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._content = content
        self.headers = httpx.Headers(headers or {})

    def read(self) -> bytes:
        return self._content

    def iter_bytes(self, chunk_size: int | None = None):
        if self._content:
            yield self._content


class ResourcesRecordingClient(RecordingVoceChatClient):
    def __init__(self) -> None:
        super().__init__()
        self.resource_file_stream_calls: list[dict[str, Any]] = []
        self.resource_file_delete_calls: list[dict[str, Any]] = []
        self.archive_create_calls: list[dict[str, Any]] = []
        self.archive_get_calls: list[dict[str, Any]] = []
        self.archive_attachment_stream_calls: list[dict[str, Any]] = []
        self.group_avatar_stream_calls: list[dict[str, Any]] = []
        self.org_logo_stream_calls: list[dict[str, Any]] = []
        self.open_graphic_calls: list[dict[str, Any]] = []
        self._file_stream_status = 200
        self._file_stream_body = b"file-bytes"
        self._attachment_stream_status = 200
        self._attachment_body = b"att-bytes"
        self._archive_json: dict[str, Any] = {
            "users": [],
            "messages": [],
            "num_attachments": 0,
        }

    @contextmanager
    def stream_resource_file_get(
        self,
        acting_uid: str,
        *,
        file_path: str,
        thumbnail: bool = False,
        download: bool = False,
        forward_headers: dict[str, str] | None = None,
    ):
        self.actings.append(acting_uid)
        self.resource_file_stream_calls.append(
            {
                "file_path": file_path,
                "thumbnail": thumbnail,
                "download": download,
                "forward_headers": forward_headers,
            }
        )
        yield _FakeStreamResponse(
            self._file_stream_status,
            self._file_stream_body,
            {"content-type": "application/octet-stream"},
        )

    def delete_resource_file(self, acting_uid: str, *, file_path: str) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.resource_file_delete_calls.append({"file_path": file_path})
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced", http_status=self._http_error_status
            )

    def create_message_archive(
        self, acting_uid: str, mid_list: list[int]
    ) -> str:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.archive_create_calls.append({"mid_list": list(mid_list)})
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced", http_status=self._http_error_status
            )
        return "2025/3/23/arch-uuid"

    def get_archive_info(self, acting_uid: str, *, file_path: str) -> dict[str, Any]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.archive_get_calls.append({"file_path": file_path})
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced", http_status=self._http_error_status
            )
        return dict(self._archive_json)

    @contextmanager
    def stream_resource_archive_attachment_get(
        self,
        acting_uid: str,
        *,
        file_path: str,
        attachment_id: int,
        download: bool = False,
    ):
        self.actings.append(acting_uid)
        self.archive_attachment_stream_calls.append(
            {
                "file_path": file_path,
                "attachment_id": attachment_id,
                "download": download,
            }
        )
        yield _FakeStreamResponse(
            self._attachment_stream_status,
            self._attachment_body,
            {"content-type": "image/png"},
        )

    @contextmanager
    def stream_resource_group_avatar_get(
        self,
        acting_uid: str,
        *,
        gid: int,
        forward_headers: dict[str, str] | None = None,
    ):
        self.actings.append(acting_uid)
        self.group_avatar_stream_calls.append(
            {"gid": int(gid), "forward_headers": forward_headers}
        )
        yield _FakeStreamResponse(
            200, b"g-av", {"content-type": "image/png"}
        )

    @contextmanager
    def stream_resource_organization_logo_get(
        self,
        acting_uid: str,
        *,
        cache_buster: int | None = None,
        forward_headers: dict[str, str] | None = None,
    ):
        self.actings.append(acting_uid)
        self.org_logo_stream_calls.append(
            {
                "t": cache_buster,
                "forward_headers": forward_headers,
            }
        )
        yield _FakeStreamResponse(
            200, b"logo", {"content-type": "image/png"}
        )

    def get_open_graphic_parse(
        self,
        *,
        target_url: str,
        accept_language: str | None = None,
    ) -> dict[str, Any]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.open_graphic_calls.append(
            {"url": target_url, "accept_language": accept_language}
        )
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced", http_status=self._http_error_status
            )
        return {"title": "Example", "url": target_url}


class ChatResourcesSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_vc = ResourcesRecordingClient()

        def _dep():
            yield self.fake_vc

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "resuser",
                "email": "resuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "resuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_get_resource_file_streams_and_acting_uid(self) -> None:
        r = self.client.get(
            "/me/im/resources/file",
            params={"file_path": "2025/1/1/u1"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, b"file-bytes")
        self.assertEqual(self.fake_vc.actings[-1], "1")
        self.assertEqual(len(self.fake_vc.resource_file_stream_calls), 1)
        self.assertEqual(
            self.fake_vc.resource_file_stream_calls[0]["file_path"],
            "2025/1/1/u1",
        )

    def test_delete_resource_file(self) -> None:
        r = self.client.delete(
            "/me/im/resources/file",
            params={"file_path": "2025/1/1/u1"},
        )
        self.assertEqual(r.status_code, 204, r.text)
        self.assertEqual(self.fake_vc.resource_file_delete_calls[-1]["file_path"], "2025/1/1/u1")

    def test_create_and_get_archive(self) -> None:
        c = self.client.post(
            "/me/im/resources/archive",
            json={"mid_list": [10, 20]},
        )
        self.assertEqual(c.status_code, 201, c.text)
        self.assertEqual(c.json()["file_path"], "2025/3/23/arch-uuid")
        self.assertEqual(self.fake_vc.archive_create_calls[-1]["mid_list"], [10, 20])

        g = self.client.get(
            "/me/im/resources/archive",
            params={"file_path": "2025/3/23/arch-uuid"},
        )
        self.assertEqual(g.status_code, 200, g.text)
        data = g.json()
        self.assertEqual(data["num_attachments"], 0)

    def test_archive_attachment_stream(self) -> None:
        r = self.client.get(
            "/me/im/resources/archive/attachment",
            params={"file_path": "2025/1/1/a", "attachment_id": 3},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, b"att-bytes")
        self.assertEqual(
            self.fake_vc.archive_attachment_stream_calls[-1]["attachment_id"], 3
        )

    def test_open_graphic(self) -> None:
        r = self.client.get(
            "/me/im/resources/open-graphic",
            params={"url": "https://example.com/page"},
            headers={"Accept-Language": "en-US"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["title"], "Example")
        self.assertEqual(
            self.fake_vc.open_graphic_calls[-1]["url"], "https://example.com/page"
        )
        self.assertEqual(self.fake_vc.open_graphic_calls[-1]["accept_language"], "en-US")

    def test_resource_group_avatar(self) -> None:
        r = self.client.get("/me/im/resources/group-avatar", params={"gid": 7})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, b"g-av")
        self.assertEqual(self.fake_vc.group_avatar_stream_calls[-1]["gid"], 7)

    def test_resource_organization_logo_cache_buster(self) -> None:
        r = self.client.get(
            "/me/im/resources/organization-logo",
            params={"t": 1700000000},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, b"logo")
        self.assertEqual(
            self.fake_vc.org_logo_stream_calls[-1]["t"], 1700000000
        )

    def test_missing_file_path_400(self) -> None:
        r = self.client.get("/me/im/resources/file", params={"file_path": "  "})
        self.assertEqual(r.status_code, 400)

    def test_unauthenticated_401(self) -> None:
        c = TestClient(app)
        r = c.get(
            "/me/im/resources/file",
            params={"file_path": "2025/1/1/x"},
        )
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
