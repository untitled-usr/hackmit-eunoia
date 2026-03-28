"""Request-scoped Memos HTTP client for module-05 posts (closed after the request).

Uses ``MID_AUTH_MEMOS_HTTP_TIMEOUT_SECONDS`` (not the provisioning timeout).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.settings import get_settings
from app.integrations.memos_client import MemosClient


def get_memos_client() -> Iterator[MemosClient]:
    settings = get_settings()
    if not settings.memos_base_url:
        raise HTTPException(
            status_code=503, detail="memos backend is not configured"
        )
    client = MemosClient(
        settings.memos_base_url,
        float(settings.memos_http_timeout_seconds),
        settings.downstream_acting_uid_header,
        settings.memos_admin_acting_uid,
    )
    try:
        yield client
    finally:
        client.close()


MemosClientDep = Annotated[MemosClient, Depends(get_memos_client)]
