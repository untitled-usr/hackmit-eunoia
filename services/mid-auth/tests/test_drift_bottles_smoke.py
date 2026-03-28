"""Smoke: /me/bottles* BFF routes forward acting uid."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_drift_bottles_smoke.db"
)
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_MEMOS_BASE_URL"] = "http://memos.test"
os.environ["MID_AUTH_MEMOS_ADMIN_ACTING_UID"] = "999"

from fastapi.testclient import TestClient

from app.api.deps.memos_client_dep import get_memos_client
from app.db.base import Base
from app.db.session import engine
from app.main import app

DB_FILE = Path("/tmp/mid_auth_drift_bottles_smoke.db")


class FakeMemosDriftBff:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.pick_calls: list[str] = []
        self.refresh_calls: list[str] = []
        self.get_calls: list[tuple[str, str]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.reply_calls: list[dict[str, Any]] = []

    def close(self) -> None:
        pass

    def create_drift_bottle(
        self, acting_uid: str, *, body: dict[str, Any]
    ) -> dict[str, Any]:
        self.create_calls.append((acting_uid, body))
        return {"name": "drift-bottles/mock-created"}

    def pick_drift_bottle(self, acting_uid: str) -> dict[str, Any]:
        self.pick_calls.append(acting_uid)
        return {
            "driftBottle": {"name": "drift-bottles/mock-picked"},
            "remainingPicks": -1,
        }

    def refresh_my_drift_bottle_candidates(
        self, acting_uid: str
    ) -> dict[str, Any]:
        self.refresh_calls.append(acting_uid)
        return {"refreshedCount": 12}

    def get_drift_bottle(
        self, bottle_ref: str, *, acting_uid: str
    ) -> dict[str, Any]:
        self.get_calls.append((bottle_ref, acting_uid))
        return {"name": f"drift-bottles/{bottle_ref}"}

    def search_drift_bottles(
        self,
        acting_uid: str,
        *,
        tag: str,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        self.search_calls.append(
            {
                "acting_uid": acting_uid,
                "tag": tag,
                "page_size": page_size,
                "page_token": page_token,
            }
        )
        return {"driftBottles": [{"name": "drift-bottles/mock-picked", "tags": [tag]}]}

    def reply_drift_bottle(
        self,
        acting_uid: str,
        bottle_ref: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        self.reply_calls.append(
            {
                "acting_uid": acting_uid,
                "bottle_ref": bottle_ref,
                "body": body,
            }
        )
        return {"name": "memos/mock-comment", "content": body.get("content", "")}


class DriftBottlesSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("bad db path")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake = FakeMemosDriftBff()

        def _dep():
            yield self.fake

        app.dependency_overrides[get_memos_client] = _dep
        self.client = TestClient(app)
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "drift-smoke",
                "email": "drift-smoke@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "drift-smoke", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_create_pick_refresh_get_use_acting_uid(self) -> None:
        c = self.client.post("/me/bottles", json={"content": "hello drift"})
        self.assertEqual(c.status_code, 200, c.text)
        self.assertEqual(len(self.fake.create_calls), 1)
        acting, body = self.fake.create_calls[0]
        self.assertEqual(acting, "1")
        self.assertEqual(body["content"], "hello drift")

        p = self.client.post("/me/bottles/pick")
        self.assertEqual(p.status_code, 200, p.text)
        self.assertEqual(self.fake.pick_calls, ["1"])

        r = self.client.post("/me/bottles/refresh")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.fake.refresh_calls, ["1"])

        g = self.client.get("/me/bottles/mock-picked")
        self.assertEqual(g.status_code, 200, g.text)
        self.assertEqual(self.fake.get_calls, [("mock-picked", "1")])

        s = self.client.get("/me/bottles/search?tag=stress&pageSize=5&pageToken=10")
        self.assertEqual(s.status_code, 200, s.text)
        self.assertEqual(
            self.fake.search_calls,
            [
                {
                    "acting_uid": "1",
                    "tag": "stress",
                    "page_size": 5,
                    "page_token": "10",
                }
            ],
        )

        reply = self.client.post(
            "/me/bottles/mock-picked/reply",
            json={"content": "hug for you"},
        )
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(
            self.fake.reply_calls,
            [
                {
                    "acting_uid": "1",
                    "bottle_ref": "mock-picked",
                    "body": {"content": "hug for you"},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
