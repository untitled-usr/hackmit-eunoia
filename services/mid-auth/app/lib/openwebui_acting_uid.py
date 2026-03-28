"""Resolve OpenWebUI ``X-Acting-Uid`` from ``user_app_mappings.app_uid`` (module-07)."""

from __future__ import annotations


class OpenWebUIAppUidError(ValueError):
    """app_uid is missing or blank after strip."""


def openwebui_acting_uid_header_value(app_uid: str) -> str:
    """
    Value for OpenWebUI ``X-Acting-Uid`` header.

    v1: no strict UUID validation — any non-empty stripped string is passed through.
    """
    raw = (app_uid or "").strip()
    if not raw:
        raise OpenWebUIAppUidError("empty app_uid")
    return raw
