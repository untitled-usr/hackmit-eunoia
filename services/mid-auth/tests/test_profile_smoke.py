import os
import unittest
from pathlib import Path

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_profile_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app

DB_FILE = Path("/tmp/mid_auth_profile_smoke.db")


class ProfileSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)
        self._register_and_login()

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(bind=engine)

    def _register_and_login(self) -> None:
        register_response = self.client.post(
            "/auth/register",
            json={
                "username": " ProfileUser ",
                "email": " ProfileUser@example.com ",
                "password": "Secret123!",
            },
        )
        self.assertEqual(register_response.status_code, 201)

        login_response = self.client.post(
            "/auth/login",
            json={"identifier": "profileuser", "password": "Secret123!"},
        )
        self.assertEqual(login_response.status_code, 200)

    def test_get_me_profile_success(self) -> None:
        response = self.client.get("/me/profile")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["username"], "profileuser")
        self.assertEqual(payload["email"], "profileuser@example.com")
        self.assertEqual(payload["display_name"], "profileuser")
        self.assertIsNone(payload["gender"])
        self.assertIsNone(payload["description"])
        self.assertIsNone(payload["avatar_source"])
        self.assertIsNone(payload["avatar_url"])

    def test_patch_me_profile_success(self) -> None:
        response = self.client.patch(
            "/me/profile",
            json={
                "display_name": "  新名字 😄  ",
                "username": "  NewName  ",
                "email": " NewName@example.com ",
                "gender": " male ",
                "description": "  hello world  ",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["display_name"], "新名字 😄")
        self.assertEqual(payload["username"], "newname")
        self.assertEqual(payload["email"], "newname@example.com")
        self.assertEqual(payload["gender"], "male")
        self.assertEqual(payload["description"], "hello world")
        self.assertIsNone(payload["avatar_source"])
        self.assertIsNone(payload["avatar_url"])

    def test_patch_me_profile_invalid_session_401(self) -> None:
        self.client.cookies.clear()
        response = self.client.patch("/me/profile", json={"display_name": "new-name"})
        self.assertEqual(response.status_code, 401)

    def test_patch_me_profile_empty_display_name_400(self) -> None:
        response = self.client.patch("/me/profile", json={"display_name": "   "})
        self.assertEqual(response.status_code, 400)

    def test_patch_me_profile_too_long_display_name_validation(self) -> None:
        response = self.client.patch("/me/profile", json={"display_name": "a" * 65})
        self.assertIn(response.status_code, (400, 422))

    def test_patch_me_profile_with_extra_forbidden_field_422(self) -> None:
        response = self.client.patch(
            "/me/profile",
            json={"display_name": "valid-name", "unknown_field": "x"},
        )
        self.assertEqual(response.status_code, 422)

    def test_patch_me_profile_username_conflict_409(self) -> None:
        r2 = self.client.post(
            "/auth/register",
            json={
                "username": "another",
                "email": "another@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r2.status_code, 201)
        response = self.client.patch("/me/profile", json={"username": "another"})
        self.assertEqual(response.status_code, 409)

    def test_patch_me_profile_email_conflict_409(self) -> None:
        r2 = self.client.post(
            "/auth/register",
            json={
                "username": "another2",
                "email": "another2@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r2.status_code, 201)
        response = self.client.patch("/me/profile", json={"email": "another2@example.com"})
        self.assertEqual(response.status_code, 409)

    def test_get_me_profile_avatar_fields_are_null(self) -> None:
        response = self.client.get("/me/profile")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["avatar_source"])
        self.assertIsNone(payload["avatar_url"])

    def test_me_avatar_404_when_missing(self) -> None:
        r = self.client.get("/me/avatar")
        self.assertEqual(r.status_code, 404)

    def test_post_get_delete_avatar_png_round_trip(self) -> None:
        # 1×1 transparent PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        up = self.client.post(
            "/me/avatar",
            files={"file": ("x.png", png, "image/png")},
        )
        self.assertEqual(up.status_code, 204, up.text)

        prof = self.client.get("/me/profile").json()
        self.assertEqual(prof["avatar_source"], "mid-auth")
        self.assertTrue(prof["avatar_url"].startswith("/me/avatar?t="))

        av = self.client.get("/me/avatar")
        self.assertEqual(av.status_code, 200, av.text)
        self.assertEqual(av.content, png)
        self.assertEqual(av.headers.get("content-type"), "image/png")

        dl = self.client.delete("/me/avatar")
        self.assertEqual(dl.status_code, 204)
        self.assertEqual(self.client.get("/me/avatar").status_code, 404)
        p2 = self.client.get("/me/profile").json()
        self.assertIsNone(p2["avatar_source"])
        self.assertIsNone(p2["avatar_url"])

    def test_post_avatar_rejects_non_image(self) -> None:
        r = self.client.post(
            "/me/avatar",
            files={"file": ("x.bin", b"not an image", "application/octet-stream")},
        )
        self.assertEqual(r.status_code, 415)


if __name__ == "__main__":
    unittest.main()
