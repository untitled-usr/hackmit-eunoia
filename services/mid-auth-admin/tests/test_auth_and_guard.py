from __future__ import annotations

from fastapi.testclient import TestClient

from mid_auth_admin.main import app


def test_healthz_is_public() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200


def test_guard_blocks_non_public_routes_without_login() -> None:
    client = TestClient(app)
    response = client.get("/admin/users")
    assert response.status_code == 401


def test_login_logout_and_me() -> None:
    client = TestClient(app)

    bad = client.post("/auth/login", json={"username": "admin", "password": "bad"})
    assert bad.status_code == 401

    login = client.post("/auth/login", json={"username": "admin", "password": "ChangeMe123!"})
    assert login.status_code == 200
    assert login.json()["ok"] is True

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["username"] == "admin"

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    me_after = client.get("/auth/me")
    assert me_after.status_code == 401

