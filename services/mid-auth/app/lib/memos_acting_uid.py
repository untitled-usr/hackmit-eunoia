"""Resolve Memos X-Acting-Uid and list filters from platform user_app_mappings.app_uid."""

from __future__ import annotations


class MemosAppUidError(ValueError):
    """app_uid cannot be parsed as a Memos user id."""


def memos_acting_uid_header_value(app_uid: str) -> str:
    """
    Value for Memos ``X-Acting-Uid`` header (numeric string only).

    ``app_uid`` is stored as ``users/{id}`` from provision, or a bare numeric id.
    """
    uid = memos_numeric_user_id(app_uid)
    return str(uid)


def memos_numeric_user_id(app_uid: str) -> int:
    """Integer Memos user id for CEL filters such as ``creator_id == {id}``."""
    raw = (app_uid or "").strip()
    if not raw:
        raise MemosAppUidError("empty app_uid")
    if raw.startswith("users/"):
        suffix = raw.split("/", 1)[1].strip()
        if not suffix.isdigit():
            raise MemosAppUidError(f"invalid users/ id: {app_uid!r}")
        n = int(suffix)
    elif raw.isdigit():
        n = int(raw)
    else:
        raise MemosAppUidError(f"unsupported app_uid format: {app_uid!r}")
    if n <= 0:
        raise MemosAppUidError(f"invalid memos user id: {n}")
    return n


def list_memos_creator_filter(creator_id: int) -> str:
    """CEL filter: only memos owned by the acting Memos user (my-posts list, not a feed)."""
    return f"creator_id == {int(creator_id)}"
