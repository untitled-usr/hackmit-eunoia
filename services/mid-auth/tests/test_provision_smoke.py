import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_provision_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.provision_logs import ProvisionLog
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.services.provision_service import ProvisionError, ProvisionService

DB_FILE = Path("/tmp/mid_auth_provision_smoke.db")


class ProvisionSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(bind=engine)

    def test_register_creates_mappings_and_logs(self) -> None:
        response = self.client.post(
            "/auth/register",
            json={
                "username": " provuser ",
                "email": " provuser@example.com ",
                "password": "Secret123!",
            },
        )
        self.assertEqual(response.status_code, 201)

        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "provuser").first()
            self.assertIsNotNone(user)
            assert user is not None
            mappings = (
                db.query(UserAppMapping)
                .filter(UserAppMapping.user_id == user.id)
                .all()
            )
            self.assertEqual(len(mappings), 3)
            names = {m.app_name for m in mappings}
            self.assertEqual(names, {"openwebui", "vocechat", "memos"})
            logs = (
                db.query(ProvisionLog)
                .filter(ProvisionLog.user_id == user.id)
                .all()
            )
            self.assertEqual(len(logs), 3)
            for log in logs:
                self.assertEqual(log.status, "success")

    def test_register_rolls_back_when_provisioning_fails(self) -> None:
        with patch.object(
            ProvisionService,
            "provision_user",
            side_effect=ProvisionError("forced failure"),
        ):
            response = self.client.post(
                "/auth/register",
                json={
                    "username": " failuser ",
                    "email": " failuser@example.com ",
                    "password": "Secret123!",
                },
            )
        self.assertEqual(response.status_code, 503)

        with SessionLocal() as db:
            self.assertIsNone(
                db.query(User).filter(User.username == "failuser").first()
            )
            self.assertEqual(db.query(UserAppMapping).count(), 0)
            self.assertEqual(db.query(ProvisionLog).count(), 0)


if __name__ == "__main__":
    unittest.main()
