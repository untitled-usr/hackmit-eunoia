"""Request-scoped VoceChat HTTP client for module-06 (closed after the request).

Uses ``MID_AUTH_VOCECHAT_HTTP_TIMEOUT_SECONDS`` (not provisioning timeout).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.settings import get_settings
from app.integrations.vocechat_client import VoceChatClient


def get_vocechat_client() -> Iterator[VoceChatClient]:
    settings = get_settings()
    if not settings.vocechat_base_url:
        raise HTTPException(
            status_code=503, detail="vocechat backend is not configured"
        )
    client = VoceChatClient(
        settings.vocechat_base_url,
        float(settings.vocechat_http_timeout_seconds),
        settings.downstream_acting_uid_header,
        settings.vocechat_admin_acting_uid,
    )
    try:
        yield client
    finally:
        client.close()


VoceChatClientDep = Annotated[VoceChatClient, Depends(get_vocechat_client)]
