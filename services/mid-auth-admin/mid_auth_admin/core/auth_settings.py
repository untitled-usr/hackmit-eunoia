from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        out = int(value.strip())
    except ValueError:
        return default
    return out if out > 0 else default


def _as_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(x.strip() for x in value.split(",") if x.strip())


@dataclass(frozen=True)
class AuthSettings:
    admin_username: str
    admin_password_hash: str
    session_secret: str
    session_ttl_seconds: int
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    allowed_origins: tuple[str, ...]

    def validate(self) -> None:
        if not self.admin_username.strip():
            raise RuntimeError("MID_AUTH_ADMIN_USERNAME is required")
        if not self.admin_password_hash.strip():
            raise RuntimeError("MID_AUTH_ADMIN_PASSWORD_HASH is required")
        if not self.session_secret.strip():
            raise RuntimeError("MID_AUTH_ADMIN_SESSION_SECRET is required")
        if len(self.session_secret.strip()) < 16:
            raise RuntimeError("MID_AUTH_ADMIN_SESSION_SECRET must be at least 16 chars")


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    settings = AuthSettings(
        admin_username=os.getenv("MID_AUTH_ADMIN_USERNAME", "admin"),
        admin_password_hash=os.getenv("MID_AUTH_ADMIN_PASSWORD_HASH", "plain$ChangeMe123!"),
        session_secret=os.getenv("MID_AUTH_ADMIN_SESSION_SECRET", "dev-only-change-this-secret"),
        session_ttl_seconds=_as_int(os.getenv("MID_AUTH_ADMIN_SESSION_TTL_SECONDS"), 8 * 60 * 60),
        cookie_name=os.getenv("MID_AUTH_ADMIN_COOKIE_NAME", "mid_auth_admin_session"),
        cookie_secure=_as_bool(os.getenv("MID_AUTH_ADMIN_COOKIE_SECURE"), False),
        cookie_samesite=os.getenv("MID_AUTH_ADMIN_COOKIE_SAMESITE", "lax").strip().lower(),
        allowed_origins=_as_list(os.getenv("MID_AUTH_ADMIN_ALLOWED_ORIGINS")),
    )
    if settings.cookie_samesite not in {"lax", "strict", "none"}:
        settings = AuthSettings(
            admin_username=settings.admin_username,
            admin_password_hash=settings.admin_password_hash,
            session_secret=settings.session_secret,
            session_ttl_seconds=settings.session_ttl_seconds,
            cookie_name=settings.cookie_name,
            cookie_secure=settings.cookie_secure,
            cookie_samesite="lax",
            allowed_origins=settings.allowed_origins,
        )
    settings.validate()
    return settings

