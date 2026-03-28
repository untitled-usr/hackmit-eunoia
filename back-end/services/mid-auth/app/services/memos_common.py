"""Shared Memos HTTP error mapping for mid-auth BFF routes."""

from __future__ import annotations

from app.integrations.memos_client import MemosClientError


def memos_client_http_tuple(exc: MemosClientError) -> tuple[int, str]:
    """Map ``MemosClientError`` to ``(status_code, detail)`` for ``HTTPException``."""
    if exc.transport:
        return 503, "memos backend unavailable"
    msg = str(exc).lower()
    if "admin acting uid is not configured" in msg:
        return 503, "memos admin is not configured"
    if "archived" in msg or "user is archived" in msg:
        return 403, "memos user is disabled"
    code = exc.http_status
    if code == 404:
        return 404, "memos resource not found"
    if code == 403:
        return 403, "forbidden"
    if code == 401:
        return 401, "memos authentication failed"
    if code == 400:
        return 400, "invalid request to memos backend"
    if code is not None and code >= 500:
        return 503, "memos backend error"
    return 503, "memos backend error"
