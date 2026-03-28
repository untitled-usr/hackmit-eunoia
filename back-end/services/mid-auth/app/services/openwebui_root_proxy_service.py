"""BFF: proxy Open WebUI root paths used by the forked frontend (``/api/config``, ``/ollama``, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.integrations.openwebui_client import (
    OpenWebUIClient,
    OpenWebUIClientError,
    filter_openwebui_proxy_response_headers,
)
from app.models.users import User
from app.services.ai_chat_service import (
    AiChatServiceError,
    resolve_openwebui_acting_uid,
)

log = logging.getLogger(__name__)


def map_openwebui_proxy_client_error(exc: OpenWebUIClientError) -> HTTPException:
    """Map upstream errors to client HTTP errors (never echo downstream body or transport host)."""
    if exc.transport:
        return HTTPException(status_code=503, detail="openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return HTTPException(status_code=503, detail="openwebui response error")
    if status >= 500:
        return HTTPException(status_code=503, detail="openwebui upstream error")
    if status == 401:
        return HTTPException(status_code=401, detail="unauthorized")
    if status == 403:
        return HTTPException(status_code=403, detail="forbidden")
    if status == 404:
        return HTTPException(status_code=404, detail="not found")
    if status == 422:
        return HTTPException(status_code=422, detail="invalid request")
    if 400 <= status < 500:
        return HTTPException(status_code=status, detail="openwebui request rejected")
    return HTTPException(status_code=503, detail="openwebui upstream error")


def forwardable_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("content-type", "accept", "accept-language"):
        v = request.headers.get(key)
        if v:
            out[key] = v
    return out


def should_proxy_stream(request: Request, body: bytes) -> bool:
    if request.method.upper() != "POST":
        return False
    accept = request.headers.get("accept", "").lower()
    if "text/event-stream" in accept:
        return True
    if body and body[:1] == b"{":
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict) and payload.get("stream") is True:
                return True
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            pass
    return False


def resolve_acting_uid(db: Session, user: User) -> str:
    try:
        return resolve_openwebui_acting_uid(db, user)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def resolve_acting_uid_optional(db: Session, user: User | None) -> str | None:
    """Acting Open Web UI uid when logged in and mapped; else ``None`` (anonymous upstream call)."""
    if user is None:
        return None
    try:
        return resolve_openwebui_acting_uid(db, user)
    except AiChatServiceError:
        return None


def proxy_non_stream(
    ow: OpenWebUIClient,
    acting_uid: str | None,
    *,
    method: str,
    downstream_path: str,
    params: list[tuple[str, str]],
    body: bytes,
    extra_headers: dict[str, str],
) -> Any:
    from starlette.responses import Response

    try:
        upstream = ow.proxy_to_openwebui(
            acting_uid,
            method=method,
            downstream_path=downstream_path,
            params=params or None,
            content=body if body else None,
            extra_headers=extra_headers or None,
        )
    except OpenWebUIClientError as exc:
        raise map_openwebui_proxy_client_error(exc) from exc
    hdrs = filter_openwebui_proxy_response_headers(upstream.headers)
    # httpx may decode upstream content; forwarded content-length/content-encoding can become stale
    # and trigger h11 "Too much data for declared Content-Length" on response write.
    hdrs.pop("content-length", None)
    hdrs.pop("Content-Length", None)
    hdrs.pop("content-encoding", None)
    hdrs.pop("Content-Encoding", None)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=hdrs,
    )


def proxy_streaming(
    ow: OpenWebUIClient,
    acting_uid: str | None,
    *,
    method: str,
    downstream_path: str,
    params: list[tuple[str, str]],
    body: bytes,
    extra_headers: dict[str, str],
) -> Any:
    from starlette.responses import StreamingResponse

    try:
        stream_holder = ow.proxy_to_openwebui_stream(
            acting_uid,
            method=method,
            downstream_path=downstream_path,
            params=params or None,
            content=body if body else None,
            extra_headers=extra_headers or None,
        )
    except OpenWebUIClientError as exc:
        raise map_openwebui_proxy_client_error(exc) from exc

    def gen():
        yield from stream_holder.iter_bytes()

    out_headers = filter_openwebui_proxy_response_headers(stream_holder.response.headers)
    out_headers.pop("content-length", None)
    out_headers.pop("Content-Length", None)
    out_headers.pop("content-encoding", None)
    out_headers.pop("Content-Encoding", None)
    media_type = out_headers.pop("content-type", None) or "application/octet-stream"
    return StreamingResponse(
        gen(),
        status_code=stream_holder.response.status_code,
        media_type=media_type,
        headers=out_headers,
    )


async def run_proxy(
    *,
    request: Request,
    db: Session,
    user: User | None,
    ow: OpenWebUIClient,
    downstream_path: str,
    require_mid_auth_user: bool = True,
) -> Any:
    import asyncio

    if require_mid_auth_user:
        if user is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        acting_uid = resolve_acting_uid(db, user)
    else:
        acting_uid = resolve_acting_uid_optional(db, user)
    body = await request.body()
    params = list(request.query_params.multi_items())
    extra = forwardable_request_headers(request)
    use_stream = should_proxy_stream(request, body)

    if use_stream:
        return await asyncio.to_thread(
            proxy_streaming,
            ow,
            acting_uid,
            method=request.method,
            downstream_path=downstream_path,
            params=params,
            body=body,
            extra_headers=extra,
        )
    return await asyncio.to_thread(
        proxy_non_stream,
        ow,
        acting_uid,
        method=request.method,
        downstream_path=downstream_path,
        params=params,
        body=body,
        extra_headers=extra,
    )
