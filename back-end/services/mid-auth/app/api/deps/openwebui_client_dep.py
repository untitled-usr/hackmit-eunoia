"""Request-scoped OpenWebUI HTTP client for module-07 AI chats."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.settings import get_settings
from app.integrations.openwebui_client import OpenWebUIClient


def get_openwebui_client() -> Iterator[OpenWebUIClient]:
    settings = get_settings()
    if not settings.open_webui_base_url:
        raise HTTPException(
            status_code=503, detail="openwebui backend is not configured"
        )
    client = OpenWebUIClient(
        settings.open_webui_base_url,
        float(settings.openwebui_http_timeout_seconds),
        settings.downstream_acting_uid_header,
        settings.open_webui_admin_acting_uid,
    )
    try:
        yield client
    finally:
        client.close()


OpenWebUIClientDep = Annotated[OpenWebUIClient, Depends(get_openwebui_client)]
