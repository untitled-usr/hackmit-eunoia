import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_favorites_smoke.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_VOCECHAT_BASE_URL"] = "http://vocechat.test/api"

from fastapi.testclient import TestClient

from app.api.deps.vocechat_client_dep import get_vocechat_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.vocechat_client import VoceChatClientError
from app.main import app

DB_FILE = Path("/tmp/mid_auth_favorites_smoke.db")


class FakeFavoritesVoceChatClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False
        self._http_error_status: int | None = None
        self.last_attachment: dict[str, Any] | None = None

    def close(self) -> None:
        pass

    def list_favorite_archives(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        return [{"id": "f1", "created_at": 100}]

    def create_favorite_archive(
        self, acting_uid: str, mid_list: list[int]
    ) -> dict[str, Any]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        if self._http_error_status == 429:
            raise VoceChatClientError(
                "rate", http_status=429
            )
        return {"id": "new-f", "created_at": 200}

    def delete_favorite_archive(self, acting_uid: str, favorite_id: str) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        if favorite_id == "missing":
            raise VoceChatClientError("nf", http_status=404)

    def get_favorite_archive_info(
        self, acting_uid: str, favorite_id: str
    ) -> dict[str, Any]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        return {
            "users": [],
            "messages": [],
            "num_attachments": 0,
        }

    def get_favorite_attachment_bytes(
        self,
        acting_uid: str,
        owner_uid: int,
        favorite_id: str,
        attachment_id: int,
        *,
        download: bool = False,
    ) -> tuple[bytes, str | None, str | None]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.last_attachment = {
            "owner_uid": owner_uid,
            "favorite_id": favorite_id,
            "attachment_id": attachment_id,
            "download": download,
        }
        return (
            b"bin",
            "application/octet-stream",
            'attachment; filename="a.bin"',
        )


class FavoritesSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_vc = FakeFavoritesVoceChatClient()

        def _dep():
            yield self.fake_vc

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "favuser",
                "email": "favuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "favuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_list_create_get_delete_and_attachment(self) -> None:
        r = self.client.get("/me/im/favorites")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {"items": [{"id": "f1", "created_at": 100}]},
        )
        self.assertEqual(self.fake_vc.actings[-1], "1")

        c = self.client.post(
            "/me/im/favorites",
            json={"message_ids": [10, 20]},
        )
        self.assertEqual(c.status_code, 201)
        self.assertEqual(c.json()["id"], "new-f")
        self.assertEqual(self.fake_vc.actings[-1], "1")

        g = self.client.get("/me/im/favorites/new-f")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["num_attachments"], 0)

        d = self.client.delete("/me/im/favorites/new-f")
        self.assertEqual(d.status_code, 204)

        a = self.client.get(
            "/me/im/favorites/f1/attachments/42",
            params={"download": "true"},
        )
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.content, b"bin")
        self.assertEqual(self.fake_vc.last_attachment["owner_uid"], 1)
        self.assertEqual(self.fake_vc.last_attachment["favorite_id"], "f1")
        self.assertEqual(self.fake_vc.last_attachment["attachment_id"], 42)
        self.assertTrue(self.fake_vc.last_attachment["download"])

    def test_attachment_sanitizes_unsafe_content_disposition(self) -> None:
        orig = self.fake_vc.get_favorite_attachment_bytes

        def _unsafe(
            acting_uid: str,
            owner_uid: int,
            favorite_id: str,
            attachment_id: int,
            *,
            download: bool = False,
        ) -> tuple[bytes, str | None, str | None]:
            return (
                b"x",
                "application/octet-stream",
                'attachment; filename="/etc/passwd"',
            )

        self.fake_vc.get_favorite_attachment_bytes = _unsafe  # type: ignore[method-assign]
        try:
            r = self.client.get("/me/im/favorites/f1/attachments/1")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(
                r.headers.get("content-disposition"),
                'attachment; filename="attachment"',
            )
        finally:
            self.fake_vc.get_favorite_attachment_bytes = orig  # type: ignore[method-assign]

    def test_create_empty_message_ids_422(self) -> None:
        r = self.client.post("/me/im/favorites", json={"message_ids": []})
        self.assertEqual(r.status_code, 422)

    def test_create_too_many_429(self) -> None:
        self.fake_vc._http_error_status = 429
        try:
            r = self.client.post(
                "/me/im/favorites",
                json={"message_ids": [1]},
            )
            self.assertEqual(r.status_code, 429)
            self.assertEqual(
                r.json()["detail"], "too many favorite archives"
            )
        finally:
            self.fake_vc._http_error_status = None

    def test_delete_not_found_404(self) -> None:
        r = self.client.delete("/me/im/favorites/missing")
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated_401(self) -> None:
        self.client.cookies.clear()
        r = self.client.get("/me/im/favorites")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
