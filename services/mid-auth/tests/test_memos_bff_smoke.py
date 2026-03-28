"""Smoke: /me/library/* BFF (fake Memos client + acting uid from mapping)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_memos_bff_smoke.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_MEMOS_BASE_URL"] = "http://memos.test"
os.environ["MID_AUTH_MEMOS_ADMIN_ACTING_UID"] = "999"

from fastapi.testclient import TestClient

from app.api.deps.memos_client_dep import get_memos_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app

DB_FILE = Path("/tmp/mid_auth_memos_bff_smoke.db")


class FakeMemosBff:
    def __init__(self) -> None:
        self.user_stats_calls: list[tuple[str, str]] = []
        self.list_attachments_calls: list[tuple[Any, ...]] = []
        self.list_shortcuts_calls: list[tuple[str, str]] = []
        self.instance_dynamic_get_calls: list[dict[str, Any]] = []
        self.instance_dynamic_patch_calls: list[dict[str, Any]] = []

    def close(self) -> None:
        pass

    def get_user_stats(self, user_ref: str, *, acting_uid: str) -> dict[str, Any]:
        self.user_stats_calls.append((user_ref, acting_uid))
        return {"memoCount": 3}

    def list_attachments(
        self,
        acting_uid: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        filter_expr: str | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        self.list_attachments_calls.append(
            (acting_uid, page_size, page_token, filter_expr, order_by)
        )
        return {"attachments": []}

    def list_shortcuts(
        self,
        user_ref: str,
        *,
        acting_uid: str,
    ) -> dict[str, Any]:
        self.list_shortcuts_calls.append((user_ref, acting_uid))
        return {"shortcuts": []}

    def get_instance_dynamic_setting(
        self, setting_key_path: str, *, acting_uid: str
    ) -> dict[str, Any]:
        self.instance_dynamic_get_calls.append(
            {"path": setting_key_path, "acting_uid": acting_uid}
        )
        return {
            "name": f"instance/settings/{setting_key_path.strip().lstrip('/')}",
            "generalSetting": {"disallowUserRegistration": False},
        }

    def patch_instance_dynamic_setting(
        self,
        setting_key_path: str,
        *,
        acting_uid: str,
        update_mask: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        self.instance_dynamic_patch_calls.append(
            {
                "path": setting_key_path,
                "acting_uid": acting_uid,
                "update_mask": update_mask,
                "body": body,
            }
        )
        return {
            "name": f"instance/settings/{setting_key_path.strip().lstrip('/')}",
            "memoRelatedSetting": {"disallowPublicVisibility": True},
        }


class MemosBffSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("bad db path")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake = FakeMemosBff()

        def _dep():
            yield self.fake

        app.dependency_overrides[get_memos_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "mbff",
                "email": "mbff@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "mbff", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_me_library_stats_uses_acting_uid(self) -> None:
        r = self.client.get("/me/library/stats")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.fake.user_stats_calls), 1)
        ref, acting = self.fake.user_stats_calls[0]
        self.assertEqual(ref, "1")
        self.assertEqual(acting, "1")

    def test_me_library_list_attachments_query_aliases(self) -> None:
        r = self.client.get(
            "/me/library/attachments?pageSize=7&orderBy=createTime%20desc"
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.fake.list_attachments_calls), 1)
        acting, ps, pt, flt, ob = self.fake.list_attachments_calls[0]
        self.assertEqual(acting, "1")
        self.assertEqual(ps, 7)
        self.assertIsNone(pt)
        self.assertIsNone(flt)
        self.assertEqual(ob, "createTime desc")

    def test_me_library_list_shortcuts_forwards_user_and_acting(self) -> None:
        r = self.client.get("/me/library/shortcuts")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.fake.list_shortcuts_calls), 1)
        user_ref, acting = self.fake.list_shortcuts_calls[0]
        self.assertEqual(user_ref, "1")
        self.assertEqual(acting, "1")

    def test_me_library_instance_settings_uses_acting_and_update_mask(self) -> None:
        r = self.client.get("/me/library/instance/settings/general")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.fake.instance_dynamic_get_calls), 1)
        self.assertEqual(
            self.fake.instance_dynamic_get_calls[0],
            {"path": "general", "acting_uid": "1"},
        )
        body = r.json()
        self.assertEqual(body["name"], "instance/settings/general")
        self.assertIn("general_setting", body)
        self.assertFalse(body["general_setting"]["disallowUserRegistration"])

        p = self.client.patch(
            "/me/library/instance/settings/memo-related?updateMask=memoRelatedSetting.disallowPublicVisibility",
            json={"memoRelatedSetting": {"disallowPublicVisibility": True}},
        )
        self.assertEqual(p.status_code, 200, p.text)
        self.assertEqual(len(self.fake.instance_dynamic_patch_calls), 1)
        c = self.fake.instance_dynamic_patch_calls[0]
        self.assertEqual(c["path"], "memo-related")
        self.assertEqual(c["acting_uid"], "1")
        self.assertEqual(
            c["update_mask"],
            "memoRelatedSetting.disallowPublicVisibility",
        )
        self.assertTrue(p.json()["memo_related_setting"]["disallowPublicVisibility"])

    def test_openapi_excludes_me_memos_paths(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertNotIn("/me/memos/stats", schema["paths"])

    def test_me_memos_stats_not_routed(self) -> None:
        r = self.client.get("/me/memos/stats")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
