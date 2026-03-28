"""Real TCP/HTTP tests against a running mid-auth process (not TestClient).

These tests open actual socket connections to ``MID_AUTH_LIVE_BASE_URL`` (default
``http://127.0.0.1:19000``). If nothing is listening, the whole module is skipped.

Run::

    # Terminal 1: scripts/run-mid-auth.sh (and backends if not using stub)
    # Terminal 2:
    pytest tests/test_live_tcp_e2e.py -v

Optional::

    MID_AUTH_LIVE_BASE_URL=http://api.dev.local pytest tests/test_live_tcp_e2e.py -v
    MID_AUTH_LIVE_FULL_SCRIPT=1 pytest tests/test_live_tcp_e2e.py -v  # shell e2e script
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest

LIVE_BASE = os.environ.get("MID_AUTH_LIVE_BASE_URL", "http://127.0.0.1:19000").rstrip(
    "/"
)
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
E2E_SCRIPT = WORKSPACE_ROOT / "scripts" / "e2e-mid-auth-curl.sh"


def _tcp_available() -> bool:
    try:
        with httpx.Client(base_url=LIVE_BASE, timeout=3.0) as client:
            r = client.get("/healthz")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _tcp_available(),
    reason=f"no healthy mid-auth at {LIVE_BASE} (start scripts/run-mid-auth.sh)",
)


@pytest.fixture
def http() -> httpx.Client:
    with httpx.Client(base_url=LIVE_BASE, timeout=30.0, follow_redirects=True) as c:
        yield c


def test_healthz_via_tcp(http: httpx.Client) -> None:
    r = http.get("/healthz")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_capabilities_via_tcp(http: httpx.Client) -> None:
    r = http.get("/v1/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "reserved" in body
    assert isinstance(body["reserved"], list)


def test_auth_me_unauthenticated_via_tcp(http: httpx.Client) -> None:
    r = http.get("/auth/me")
    assert r.status_code == 401


def test_register_login_profile_flow_via_tcp(http: httpx.Client) -> None:
    suffix = uuid.uuid4().hex[:12]
    username = f"tcp_{suffix}"
    email = f"{username}@example.test"
    password = "TcpLivePass123!"

    reg = http.post(
        "/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": "TCP E2E",
        },
    )
    assert reg.status_code == 201, reg.text

    bad_login = http.post(
        "/auth/login",
        json={"identifier": email, "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login = http.post(
        "/auth/login",
        json={"identifier": email, "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.cookies.get("mid_auth_session") is not None or len(login.cookies) > 0, (
        "expected Set-Cookie from /auth/login"
    )

    # Same Client persists cookies for subsequent requests (real TCP session).
    me = http.get("/auth/me")
    assert me.status_code == 200
    data = me.json()
    assert data["username"] == username
    assert data["email"] == email

    prof = http.get("/me/profile")
    assert prof.status_code == 200

    patch = http.patch(
        "/me/profile",
        json={"display_name": "TCP Patched"},
    )
    assert patch.status_code == 200
    assert patch.json()["display_name"] == "TCP Patched"


@pytest.mark.skipif(
    os.environ.get("MID_AUTH_LIVE_FULL_SCRIPT") != "1",
    reason="set MID_AUTH_LIVE_FULL_SCRIPT=1 to run the bash curl suite via subprocess",
)
def test_e2e_curl_script_full_tcp() -> None:
    assert E2E_SCRIPT.is_file(), f"missing {E2E_SCRIPT}"
    env = {**os.environ, "BASE_URL": LIVE_BASE}
    # Strict BFF when running against a supposedly full stack
    if os.environ.get("MID_AUTH_LIVE_STRICT_BFF") == "1":
        env["MID_AUTH_E2E_STRICT_DOWNSTREAM"] = "1"
    proc = subprocess.run(
        ["/bin/bash", str(E2E_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
    assert proc.returncode == 0, "e2e-mid-auth-curl.sh failed"
