"""Contract: exported OpenAPI matches gap-task-table prefix/tag expectations."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _env() -> None:
    os.environ.setdefault(
        "MID_AUTH_DATABASE_URL",
        "sqlite+pysqlite:////tmp/mid_auth_openapi_contract_test.db",
    )
    os.environ.setdefault("MID_AUTH_PROVISION_USE_STUB", "true")


def test_export_openapi_and_gap_contract_audit() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_openapi.py")],
        cwd=str(ROOT),
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "audit_gap_openapi_contract.py")],
        cwd=str(ROOT),
        check=True,
    )
