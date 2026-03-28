import os
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_openwebui_models_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_OPEN_WEBUI_BASE_URL"] = "http://openwebui.test"
os.environ["MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID"] = "default-m"

from app.api.deps.openwebui_client_dep import get_openwebui_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.openwebui_client import OpenWebUIClientError
from app.main import app
from app.models.user_app_mappings import UserAppMapping

DB_FILE = Path("/tmp/mid_auth_openwebui_models_smoke.db")


class FakeOpenWebUIModelsClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False

    def close(self) -> None:
        pass

    def list_models_workspace(
        self,
        acting_uid: str,
        *,
        query: str | None = None,
        view_option: str | None = None,
        tag: str | None = None,
        order_by: str | None = None,
        direction: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        if self._fail_transport:
            raise OpenWebUIClientError("boom", transport=True)
        self.actings.append(acting_uid)
        return {
            "items": [{"id": "m1", "name": "One"}],
            "total": 1,
            "q": query,
            "page": page,
        }

    def get_models_base(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return [{"id": "base1"}]

    def get_model_tags(self, acting_uid: str) -> list[str]:
        self.actings.append(acting_uid)
        return ["alpha", "beta"]

    def get_model_by_id(self, acting_uid: str, model_id: str) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        if model_id == "missing":
            return None
        return {"id": model_id, "name": "N"}


class OpenWebUIModelsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID"] = "default-m"
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_ow = FakeOpenWebUIModelsClient()

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
                "username": "owmuser",
                "email": "owmuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "owmuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_models_success(self) -> None:
        r = self.client.get("/me/ai/workbench/models", params={"page": 2, "query": "x"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["total"], 1)
        self.assertEqual(self.fake_ow.actings[-1], "stub-openwebui")

    def test_base_tags_detail_default(self) -> None:
        self.assertEqual(self.client.get("/me/ai/workbench/models/base").status_code, 200)
        self.assertEqual(
            self.client.get("/me/ai/workbench/models/tags").json(), ["alpha", "beta"]
        )
        d = self.client.get(
            "/me/ai/workbench/models/detail", params={"model_id": "mid/x"}
        )
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.json()["id"], "mid/x")
        g = self.client.get("/me/ai/workbench/models/default")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["id"], "default-m")

    def test_detail_missing_model_404(self) -> None:
        r = self.client.get("/me/ai/workbench/models/detail", params={"model_id": "missing"})
        self.assertEqual(r.status_code, 404)

    def test_no_mapping_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "openwebui"
            ).delete()
            db.commit()
        self.assertEqual(self.client.get("/me/ai/workbench/models").status_code, 404)

    def test_transport_503(self) -> None:
        self.fake_ow._fail_transport = True
        self.assertEqual(self.client.get("/me/ai/workbench/models").status_code, 503)

    def test_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        self.assertEqual(raw.get("/me/ai/workbench/models").status_code, 401)
        raw.close()


if __name__ == "__main__":
    unittest.main()
