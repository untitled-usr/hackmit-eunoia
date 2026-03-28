from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSettings:
    acting_uid_header: str
    vocechat_base_url: str | None
    memos_base_url: str | None
    openwebui_base_url: str | None


FIXED_ACTING_UID: dict[str, str] = {
    "vocechat": "1",
    "memos": "1",
    "openwebui": "00000000-0000-4000-8000-000000000001",
}

PROTECTED_ADMIN_USER_IDS: dict[str, str] = {
    "vocechat": "1",
    "memos": "1",
    "openwebui": "00000000-0000-4000-8000-000000000001",
}


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def get_platform_settings() -> PlatformSettings:
    return PlatformSettings(
        acting_uid_header=os.getenv("MID_AUTH_DOWNSTREAM_ACTING_UID_HEADER", "X-Acting-Uid"),
        vocechat_base_url=_optional(os.getenv("MID_AUTH_VOCECHAT_BASE_URL")),
        memos_base_url=_optional(os.getenv("MID_AUTH_MEMOS_BASE_URL")),
        openwebui_base_url=_optional(os.getenv("MID_AUTH_OPEN_WEBUI_BASE_URL")),
    )

