"""Proxy Open WebUI ``POST /api/v1/chat/completions`` with ``stream: true`` through mid-auth.

Before returning ``StreamingResponse``, the downstream connection is opened and the status
code is checked; non-2xx bodies are read and mapped to JSON HTTP errors (no fake 200 stream).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import Request

from app.core.settings import Settings
from app.integrations.openwebui_client import OpenWebUIClientError
from app.services.ai_chat_service import map_openwebui_upstream_error

log = logging.getLogger(__name__)


class OpenWebUIChatStreamError(Exception):
    """Failed before returning the streaming body (mapped to HTTP JSON error)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _map_upstream_http_error(*, http_status: int, body_text: str) -> OpenWebUIChatStreamError:
    snippet = body_text.strip()[:500] if body_text else ""
    exc = OpenWebUIClientError(
        "chat completion stream",
        http_status=http_status,
    )
    mapped = map_openwebui_upstream_error(exc)
    detail = mapped.detail
    if snippet:
        detail = f"{detail}: {snippet}"
    return OpenWebUIChatStreamError(mapped.status_code, detail)


class OpenWebUIChatCompletionsStreamSession:
    """Holds open httpx stream until ``stream_bytes`` finishes."""

    def __init__(
        self,
        *,
        request: Request,
        client: httpx.AsyncClient,
        stream_cm: Any,
        response: httpx.Response,
    ) -> None:
        self._request = request
        self._client = client
        self._stream_cm = stream_cm
        self._response = response

    @classmethod
    async def start(
        cls,
        *,
        request: Request,
        settings: Settings,
        acting_uid: str,
        body: dict[str, Any],
    ) -> OpenWebUIChatCompletionsStreamSession:
        base = settings.open_webui_base_url
        if not base:
            raise OpenWebUIChatStreamError(503, "openwebui backend is not configured")

        url = f"{base.rstrip('/')}/api/v1/chat/completions"
        hdr_name = settings.downstream_acting_uid_header.strip()
        headers: dict[str, str] = {
            hdr_name: acting_uid.strip(),
            "Content-Type": "application/json",
        }

        payload = dict(body)
        payload["stream"] = True

        read_timeout: float | None
        if settings.openwebui_stream_read_timeout_seconds <= 0:
            read_timeout = None
        else:
            read_timeout = float(settings.openwebui_stream_read_timeout_seconds)

        timeout = httpx.Timeout(
            connect=float(settings.openwebui_stream_connect_timeout_seconds),
            read=read_timeout,
            write=120.0,
            pool=30.0,
        )

        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        stream_cm = client.stream("POST", url, headers=headers, json=payload)
        try:
            response = await stream_cm.__aenter__()
        except httpx.HTTPError as exc:
            await client.aclose()
            log.warning("openwebui chat stream connect failed: %s", exc)
            mapped = map_openwebui_upstream_error(
                OpenWebUIClientError(str(exc), transport=True)
            )
            raise OpenWebUIChatStreamError(mapped.status_code, mapped.detail) from exc

        if response.status_code >= 400:
            try:
                body_bytes = await response.aread()
            finally:
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()
            detail_txt = body_bytes.decode("utf-8", errors="replace")
            raise _map_upstream_http_error(
                http_status=response.status_code, body_text=detail_txt
            )

        return cls(
            request=request,
            client=client,
            stream_cm=stream_cm,
            response=response,
        )

    def response_content_type(self) -> str:
        ct = self._response.headers.get("content-type", "").strip()
        if not ct:
            return "text/event-stream"
        return ct.split(";")[0].strip() or "text/event-stream"

    async def stream_bytes(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                if await self._request.is_disconnected():
                    break
                if chunk:
                    yield chunk
        finally:
            with contextlib.suppress(Exception):
                await self._stream_cm.__aexit__(None, None, None)
            with contextlib.suppress(Exception):
                await self._client.aclose()
