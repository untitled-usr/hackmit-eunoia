from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

TEST_DB_PATH = "/tmp/mid_auth_admin_test.sqlite3"
os.environ["MID_AUTH_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

SERVICES_DIR = Path(__file__).resolve().parents[2]
MID_AUTH_ROOT = SERVICES_DIR / "mid-auth"
if str(MID_AUTH_ROOT) not in sys.path:
    sys.path.insert(0, str(MID_AUTH_ROOT))

from app.db.base import Base  # type: ignore  # noqa: E402
from app.models import *  # type: ignore  # noqa: F403,E402
from mid_auth_admin.main import app  # noqa: E402


def _reset_db() -> None:
    engine = create_engine(os.environ["MID_AUTH_DATABASE_URL"], connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "ChangeMe123!"},
    )
    assert response.status_code == 200


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_full_crud_smoke_for_all_resources() -> None:
    _reset_db()
    client = TestClient(app)
    _login(client)
    suffix = uuid4().hex[:8]

    user_payload = {
        "id": f"user-{suffix}",
        "public_id": f"pub-{suffix}",
        "username": f"u_{suffix}",
        "email": f"{suffix}@example.com",
        "password_hash": "argon2-hash",
        "display_name": "User One",
        "is_active": True,
        "avatar_mime_type": "image/png",
        "avatar_data": base64.b64encode(b"png-bytes").decode("utf-8"),
    }
    user = client.post("/admin/users", json=user_payload)
    assert user.status_code == 201
    user_id = user.json()["id"]

    users_list = client.get("/admin/users", params={"username": user_payload["username"]})
    assert users_list.status_code == 200
    assert len(users_list.json()["items"]) == 1

    user_patch = client.patch(f"/admin/users/{user_id}", json={"display_name": "User Updated"})
    assert user_patch.status_code == 200
    assert user_patch.json()["display_name"] == "User Updated"

    mapping = client.post(
        "/admin/user_app_mappings",
        json={
            "user_id": user_id,
            "app_name": "openwebui",
            "app_uid": f"ow-{suffix}",
            "app_username": "ow-user",
        },
    )
    assert mapping.status_code == 201
    mapping_id = mapping.json()["id"]
    assert client.get(f"/admin/user_app_mappings/{mapping_id}").status_code == 200
    assert client.patch(f"/admin/user_app_mappings/{mapping_id}", json={"app_username": "ow-u2"}).status_code == 200

    session = client.post(
        "/admin/sessions",
        json={
            "session_id": f"sid-{suffix}",
            "user_id": user_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "user_agent": "pytest",
            "ip_address": "127.0.0.1",
        },
    )
    assert session.status_code == 201
    session_id = session.json()["id"]
    assert client.get(f"/admin/sessions/{session_id}").status_code == 200
    assert client.patch(f"/admin/sessions/{session_id}", json={"ip_address": "10.0.0.1"}).status_code == 200

    provision = client.post(
        "/admin/provision_logs",
        json={
            "user_id": user_id,
            "app_name": "memos",
            "status": "ok",
            "message": "created",
        },
    )
    assert provision.status_code == 201
    provision_id = provision.json()["id"]
    assert client.get(f"/admin/provision_logs/{provision_id}").status_code == 200
    assert client.patch(f"/admin/provision_logs/{provision_id}", json={"message": "updated"}).status_code == 200

    vug = client.post(
        "/admin/virtmate_user_globals",
        json={"user_id": user_id, "config_json": {"mode": "casual"}},
    )
    assert vug.status_code == 201
    vug_id = vug.json()["id"]
    assert client.get(f"/admin/virtmate_user_globals/{vug_id}").status_code == 200
    assert (
        client.patch(f"/admin/virtmate_user_globals/{vug_id}", json={"config_json": {"mode": "strict"}}).status_code
        == 200
    )

    vss = client.post(
        "/admin/virtmate_session_settings",
        json={"user_id": user_id, "session_id": "s1", "settings_json": {"voice": "en-US"}},
    )
    assert vss.status_code == 201
    vss_id = vss.json()["id"]
    assert client.get(f"/admin/virtmate_session_settings/{vss_id}").status_code == 200
    assert (
        client.patch(f"/admin/virtmate_session_settings/{vss_id}", json={"settings_json": {"voice": "zh-CN"}}).status_code
        == 200
    )

    vst = client.post(
        "/admin/virtmate_session_states",
        json={"user_id": user_id, "session_id": "s1", "state_json": {"turn": 1}},
    )
    assert vst.status_code == 201
    vst_id = vst.json()["id"]
    assert client.get(f"/admin/virtmate_session_states/{vst_id}").status_code == 200
    assert client.patch(f"/admin/virtmate_session_states/{vst_id}", json={"state_json": {"turn": 2}}).status_code == 200

    vsm = client.post(
        "/admin/virtmate_session_messages",
        json={"user_id": user_id, "session_id": "s1", "role": "user", "content": "hello"},
    )
    assert vsm.status_code == 201
    vsm_id = vsm.json()["id"]
    assert client.get(f"/admin/virtmate_session_messages/{vsm_id}").status_code == 200
    assert client.patch(f"/admin/virtmate_session_messages/{vsm_id}", json={"content": "hello2"}).status_code == 200

    assert client.delete(f"/admin/virtmate_session_messages/{vsm_id}").status_code == 204
    assert client.delete(f"/admin/virtmate_session_states/{vst_id}").status_code == 204
    assert client.delete(f"/admin/virtmate_session_settings/{vss_id}").status_code == 204
    assert client.delete(f"/admin/virtmate_user_globals/{vug_id}").status_code == 204
    assert client.delete(f"/admin/provision_logs/{provision_id}").status_code == 204
    assert client.delete(f"/admin/sessions/{session_id}").status_code == 204
    assert client.delete(f"/admin/user_app_mappings/{mapping_id}").status_code == 204
    assert client.delete(f"/admin/users/{user_id}").status_code == 204

