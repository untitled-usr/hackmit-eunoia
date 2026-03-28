import os
import re
import unittest
from pathlib import Path

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_auth_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.sessions import UserSession
from app.models.users import User

DB_FILE = Path("/tmp/mid_auth_auth_smoke.db")
PUBLIC_ID_RE = re.compile(r"^[1-9][0-9]{7,}$")


class AuthSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(bind=engine)

    def _register_default_user(self) -> None:
        response = self.client.post(
            "/auth/register",
            json={
                "username": " Alice ",
                "email": " Alice@example.com ",
                "password": "Secret123!",
            },
        )
        self.assertEqual(response.status_code, 201)

    def test_register_success(self) -> None:
        self._register_default_user()
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "alice").first()
            self.assertIsNotNone(user)
            assert user is not None
            self.assertEqual(user.email, "alice@example.com")
            self.assertEqual(user.display_name, "alice")
            self.assertRegex(user.public_id, PUBLIC_ID_RE)

    def test_public_id_is_numeric_and_unique(self) -> None:
        r1 = self.client.post(
            "/auth/register",
            json={
                "username": "u1",
                "email": "u1@example.com",
                "password": "Secret123!",
            },
        )
        r2 = self.client.post(
            "/auth/register",
            json={
                "username": "u2",
                "email": "u2@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        p1 = r1.json()["user"]["public_id"]
        p2 = r2.json()["user"]["public_id"]
        self.assertRegex(p1, PUBLIC_ID_RE)
        self.assertRegex(p2, PUBLIC_ID_RE)
        self.assertNotEqual(p1, p2)

    def test_login_success_and_cookie_set(self) -> None:
        self._register_default_user()
        response = self.client.post(
            "/auth/login",
            json={"identifier": " Alice@Example.com ", "password": "Secret123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("set-cookie", response.headers)
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIsNotNone(response.cookies.get("mid_auth_session"))

    def test_me_success(self) -> None:
        self._register_default_user()
        login_response = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "Secret123!"},
        )
        self.assertEqual(login_response.status_code, 200)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], "alice")

    def test_logout_invalidates_current_session(self) -> None:
        self._register_default_user()
        login_response = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "Secret123!"},
        )
        self.assertEqual(login_response.status_code, 200)

        logout_response = self.client.post("/auth/logout")
        self.assertEqual(logout_response.status_code, 200)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 401)

    def test_change_password_invalidates_all_sessions(self) -> None:
        self._register_default_user()
        first_login = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "Secret123!"},
        )
        self.assertEqual(first_login.status_code, 200)

        second_login = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "Secret123!"},
        )
        self.assertEqual(second_login.status_code, 200)

        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "alice").first()
            self.assertIsNotNone(user)
            assert user is not None
            sessions_count = (
                db.query(UserSession).filter(UserSession.user_id == user.id).count()
            )
            self.assertEqual(sessions_count, 2)

        change_response = self.client.post(
            "/auth/change-password",
            json={"old_password": "Secret123!", "new_password": "NewSecret123!"},
        )
        self.assertEqual(change_response.status_code, 200)

        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "alice").first()
            assert user is not None
            sessions_count = (
                db.query(UserSession).filter(UserSession.user_id == user.id).count()
            )
            self.assertEqual(sessions_count, 0)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 401)

        old_login = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "Secret123!"},
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/auth/login",
            json={"identifier": "alice", "password": "NewSecret123!"},
        )
        self.assertEqual(new_login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
