import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_openwebui_chats_extra.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"
os.environ["MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID"] = "test-model"

from fastapi.testclient import TestClient

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.user_app_mappings import UserAppMapping

DB_FILE = Path("/tmp/mid_auth_openwebui_chats_extra.db")


class FakeOpenWebUIChatsClient:
    """Stub for Open WebUI chat-extra BFF routes."""

    def __init__(self) -> None:
        self.actings: list[str] = []
        self.last_search: tuple[str, int | None] | None = None
        self.last_tag_filter: dict[str, Any] | None = None

    def close(self) -> None:
        return None

    def search_chats(
        self,
        acting_uid: str,
        *,
        text: str,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        self.last_search = (text, page)
        return [
            {
                "id": "chat-search-1",
                "title": "Found",
                "updated_at": 10,
                "created_at": 9,
            }
        ]

    def list_pinned_chats(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return []

    def list_archived_chats(
        self,
        acting_uid: str,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = (page, query, order_by, direction)
        return []

    def list_shared_chats(
        self,
        acting_uid: str,
        *,
        page: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = (page, query, order_by, direction)
        return [
            {
                "id": "s1",
                "title": "Shared",
                "share_id": "shr1",
                "updated_at": 1,
                "created_at": 1,
            }
        ]

    def get_shared_chat_by_share_id(
        self, acting_uid: str, share_id: str
    ) -> dict[str, Any]:
        self.actings.append(acting_uid)
        return {
            "id": "x",
            "title": "Shared body",
            "share_id": share_id,
            "chat": {"title": "Shared body"},
        }

    def list_all_user_tags(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return [{"id": "t1", "name": "work", "user_id": acting_uid}]

    def list_chats_by_tag_name(
        self,
        acting_uid: str,
        *,
        name: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        self.last_tag_filter = {"name": name, "skip": skip, "limit": limit}
        return []

    def get_chat_pinned_flag(self, acting_uid: str, chat_id: str) -> bool | None:
        self.actings.append(acting_uid)
        _ = chat_id
        return False

    def toggle_chat_pin(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        return {"id": chat_id, "pinned": True, "title": "Hi"}

    def toggle_chat_archive(self, acting_uid: str, chat_id: str) -> dict[str, Any]:
        self.actings.append(acting_uid)
        return {"id": chat_id, "archived": True, "title": "Hi"}

    def get_chat_tags(self, acting_uid: str, chat_id: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = chat_id
        return []

    def add_chat_tag(
        self, acting_uid: str, chat_id: str, *, name: str
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = chat_id
        return [{"id": "n", "name": name, "user_id": acting_uid}]

    def delete_chat_tag(
        self, acting_uid: str, chat_id: str, *, name: str
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = (chat_id, name)
        return []

    def delete_all_chat_tags(self, acting_uid: str, chat_id: str) -> bool:
        self.actings.append(acting_uid)
        _ = chat_id
        return True

    def archive_all_chats(self, acting_uid: str) -> bool:
        self.actings.append(acting_uid)
        return True

    def unarchive_all_chats(self, acting_uid: str) -> bool:
        self.actings.append(acting_uid)
        return True


class OpenWebUIChatsExtraSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIChatsClient()

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
                "username": "owcextra",
                "email": "owcextra@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owcextra", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_search_uses_acting_uid_and_returns_list(self) -> None:
        r = self.client.get("/me/ai/workbench/chats/search", params={"text": "hello"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "chat-search-1")
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")
        self.assertEqual(self.fake_ow.last_search, ("hello", None))

    def test_no_openwebui_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        r = self.client.get("/me/ai/workbench/chats/pinned")
        self.assertEqual(r.status_code, 404)

    def test_shared_and_share_by_id(self) -> None:
        r = self.client.get("/me/ai/workbench/chats/shared")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        g = self.client.get("/me/ai/workbench/chats/shares/shr1")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["share_id"], "shr1")

    def test_tag_catalog_and_filter(self) -> None:
        c = self.client.get("/me/ai/workbench/chats/tag-catalog")
        self.assertEqual(c.status_code, 200)
        self.assertEqual(c.json()[0]["name"], "work")
        f = self.client.post(
            "/me/ai/workbench/chats/tag-filter",
            json={"name": "work", "skip": 0, "limit": 10},
        )
        self.assertEqual(f.status_code, 200)
        self.assertEqual(
            self.fake_ow.last_tag_filter,
            {"name": "work", "skip": 0, "limit": 10},
        )

    def test_pin_archive_tags_and_bulk(self) -> None:
        p = self.client.get("/me/ai/workbench/chats/c1/pinned")
        self.assertEqual(p.status_code, 200)
        self.assertEqual(p.json()["pinned"], False)
        tp = self.client.post("/me/ai/workbench/chats/c1/pin")
        self.assertEqual(tp.status_code, 200)
        self.assertEqual(tp.json()["pinned"], True)
        ta = self.client.post("/me/ai/workbench/chats/c1/archive")
        self.assertEqual(ta.status_code, 200)
        self.assertEqual(ta.json()["archived"], True)
        add = self.client.post(
            "/me/ai/workbench/chats/c1/tags",
            json={"name": "alpha"},
        )
        self.assertEqual(add.status_code, 200)
        dele = self.client.request(
            "DELETE",
            "/me/ai/workbench/chats/c1/tags",
            json={"name": "alpha"},
        )
        self.assertEqual(dele.status_code, 200)
        clr = self.client.delete("/me/ai/workbench/chats/c1/tags/all")
        self.assertEqual(clr.status_code, 200)
        self.assertEqual(clr.json()["ok"], True)
        aa = self.client.post("/me/ai/workbench/chats/archive-all")
        self.assertEqual(aa.status_code, 200)
        self.assertEqual(aa.json()["ok"], True)
        ua = self.client.post("/me/ai/workbench/chats/unarchive-all")
        self.assertEqual(ua.status_code, 200)
        self.assertEqual(ua.json()["ok"], True)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.get("/me/ai/workbench/chats/pinned")
        self.assertEqual(r.status_code, 401)
        raw.close()


if __name__ == "__main__":
    unittest.main()
