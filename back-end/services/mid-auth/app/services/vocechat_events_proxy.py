"""Proxy VoceChat ``GET /user/events`` (SSE) through mid-auth.

v1 is a transparent ``text/event-stream`` pipe: platform path ``GET /me/im/events``,
downstream URL built from settings (VoceChat ``/api`` base + ``/user/events``). Clients
never see VoceChat paths in JSON; the stream body is opaque event frames.

**Why this is not “plain HTTP”:** Unlike other chat routes, this keeps a long-lived
downstream connection. Operators should either pin users to one mid-auth worker (ingress
sticky sessions) or enable ``MID_AUTH_VOCECHAT_SSE_REDIS_URL`` so a short-lived Redis
lease blocks a second concurrent stream for the same platform user on another worker.

**Upstream errors:** The upstream connection and status check run *before* returning
``StreamingResponse``, so non-2xx VoceChat responses still map to normal JSON HTTP
errors (never a misleading 200 + empty stream).

**Backpressure:** Bytes are forwarded as they arrive; if the browser disconnects, the
upstream stream is stopped. Slow readers rely on TCP / ASGI backpressure.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import redis
from fastapi import Request

from app.core.settings import Settings
from app.integrations.vocechat_client import build_vocechat_user_events_url

log = logging.getLogger(__name__)


class VoceChatEventStreamError(Exception):
    """Failed before or while setting up the upstream stream (mapped to HTTP)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _map_upstream_http_status(status: int) -> tuple[int, str]:
    if status == 401:
        return 401, "chat authentication failed"
    if status == 403:
        return 403, "forbidden"
    if status == 404:
        return 404, "chat resource not found"
    if status == 400:
        return 400, "invalid request to chat backend"
    if status >= 500:
        return 503, "chat backend error"
    return 503, "chat backend error"


def _release_redis_lease(
    r: redis.Redis | None,
    lease_key: str | None,
    lease_token: str | None,
) -> None:
    if r is None or lease_key is None or lease_token is None:
        return
    try:
        if r.get(lease_key) == lease_token:
            r.delete(lease_key)
    except redis.RedisError:
        log.warning("redis lease cleanup failed for %s", lease_key)
    try:
        r.close()
    except redis.RedisError:
        pass


class VoceChatSseSession:
    """Holds Redis lease + open httpx stream until ``stream_bytes`` finishes."""

    def __init__(
        self,
        *,
        request: Request,
        client: httpx.AsyncClient,
        stream_cm: Any,
        response: httpx.Response,
        r: redis.Redis | None,
        lease_key: str | None,
        lease_token: str | None,
    ) -> None:
        self._request = request
        self._client = client
        self._stream_cm = stream_cm
        self._response = response
        self._r = r
        self._lease_key = lease_key
        self._lease_token = lease_token

    @classmethod
    async def start(
        cls,
        *,
        request: Request,
        settings: Settings,
        acting_uid: str,
        user_id: str,
        after_mid: int | None,
        users_version: int | None,
    ) -> VoceChatSseSession:
        base = settings.vocechat_base_url
        if not base:
            raise VoceChatEventStreamError(503, "vocechat backend is not configured")

        url = build_vocechat_user_events_url(
            base.rstrip("/"),
            after_mid=after_mid,
            users_version=users_version,
        )
        hdr = settings.downstream_acting_uid_header.strip()
        headers: dict[str, str] = {hdr: acting_uid.strip()}
        cookie = request.headers.get("cookie")
        if cookie:
            headers["Cookie"] = cookie

        read_timeout: float | None
        if settings.vocechat_sse_read_timeout_seconds <= 0:
            read_timeout = None
        else:
            read_timeout = float(settings.vocechat_sse_read_timeout_seconds)

        timeout = httpx.Timeout(
            connect=float(settings.vocechat_sse_connect_timeout_seconds),
            read=read_timeout,
            write=30.0,
            pool=30.0,
        )

        lease_key: str | None = None
        lease_token: str | None = None
        r: redis.Redis | None = None
        if settings.vocechat_sse_redis_url:
            prefix = settings.vocechat_sse_redis_key_prefix.strip() or "midauth:vc_sse"
            lease_key = f"{prefix}:user:{user_id}"
            lease_token = (
                (settings.vocechat_sse_instance_id or "").strip()
                or f"pid-{os.getpid()}"
            )
            r = redis.from_url(settings.vocechat_sse_redis_url, decode_responses=True)
            ok = bool(
                r.set(
                    lease_key,
                    lease_token,
                    nx=True,
                    ex=int(settings.vocechat_sse_redis_lease_seconds),
                )
            )
            if not ok:
                r.close()
                raise VoceChatEventStreamError(
                    409, "another chat event stream is already active for this user"
                )

        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        stream_cm = client.stream("GET", url, headers=headers)
        try:
            response = await stream_cm.__aenter__()
        except httpx.HTTPError as exc:
            await client.aclose()
            _release_redis_lease(r, lease_key, lease_token)
            raise VoceChatEventStreamError(
                503, f"chat backend unavailable: {exc}"
            ) from exc

        if response.status_code >= 400:
            try:
                body = await response.aread()
            finally:
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()
            _release_redis_lease(r, lease_key, lease_token)
            detail = body.decode("utf-8", errors="replace")[:500]
            code, msg = _map_upstream_http_status(response.status_code)
            if detail.strip():
                msg = f"{msg}: {detail.strip()}"
            raise VoceChatEventStreamError(code, msg)

        return cls(
            request=request,
            client=client,
            stream_cm=stream_cm,
            response=response,
            r=r,
            lease_key=lease_key,
            lease_token=lease_token,
        )

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
            _release_redis_lease(self._r, self._lease_key, self._lease_token)
