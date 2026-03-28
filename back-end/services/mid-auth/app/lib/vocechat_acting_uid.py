"""Resolve VoceChat ``X-Acting-Uid`` from ``user_app_mappings.app_uid`` (module-06)."""

from __future__ import annotations


class VoceChatAppUidError(ValueError):
    """app_uid cannot be parsed as a VoceChat user id."""


def vocechat_acting_uid_header_value(app_uid: str) -> str:
    """
    Value for VoceChat ``X-Acting-Uid`` header (numeric string).

    Provision stores ``vocechat_uid`` as a decimal string (e.g. ``\"42\"``).
    """
    n = vocechat_numeric_user_id(app_uid)
    return str(n)


def vocechat_numeric_user_id(app_uid: str) -> int:
    """Integer VoceChat user id (e.g. for path segments)."""
    raw = (app_uid or "").strip()
    if not raw:
        raise VoceChatAppUidError("empty app_uid")
    if not raw.isdigit():
        raise VoceChatAppUidError(f"unsupported app_uid format: {app_uid!r}")
    n = int(raw)
    if n <= 0:
        raise VoceChatAppUidError(f"invalid vocechat user id: {n}")
    return n
