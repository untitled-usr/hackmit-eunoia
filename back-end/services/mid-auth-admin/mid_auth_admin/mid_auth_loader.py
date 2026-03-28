from __future__ import annotations

import sys
from pathlib import Path


def _ensure_mid_auth_on_path() -> None:
    services_dir = Path(__file__).resolve().parents[2]
    mid_auth_root = services_dir / "mid-auth"
    path_text = str(mid_auth_root)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


_ensure_mid_auth_on_path()

# noqa: E402 - imported after sys.path injection by design
from app.db.session import get_db as get_mid_auth_db  # type: ignore  # noqa: E402
from app.models.provision_logs import ProvisionLog  # type: ignore  # noqa: E402
from app.models.sessions import UserSession  # type: ignore  # noqa: E402
from app.models.user_app_mappings import UserAppMapping  # type: ignore  # noqa: E402
from app.models.users import User  # type: ignore  # noqa: E402
from app.models.virtmate import (  # type: ignore  # noqa: E402
    VirtmateSessionMessage,
    VirtmateSessionSettings,
    VirtmateSessionState,
    VirtmateUserGlobal,
)

