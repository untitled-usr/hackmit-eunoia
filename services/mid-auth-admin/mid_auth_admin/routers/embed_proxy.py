from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, status
from starlette.responses import Response as StarletteResponse
from starlette.websockets import WebSocketDisconnect

from mid_auth_admin.core.auth_session import (
    extract_token_from_websocket_scope,
    headers_bytes_to_dict,
    parse_cookie_header,
    parse_session_token,
)
from mid_auth_admin.core.auth_settings import get_auth_settings
from mid_auth_admin.core.platform_settings import get_platform_settings

try:
    import websockets
except Exception:  # noqa: BLE001
    websockets = None

router = APIRouter()

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _base_url_for_platform(platform: str) -> str:
    settings = get_platform_settings()
    mapping = {
        "openwebui": settings.openwebui_base_url,
        "vocechat": settings.vocechat_base_url,
        "memos": settings.memos_base_url,
    }
    base = mapping.get(platform)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"base url for {platform} is not configured",
        )
    return base.rstrip("/")


def _build_target_url(base_url: str, tail_path: str, query_items: Iterable[tuple[str, str]]) -> str:
    normalized_path = f"/{tail_path.lstrip('/')}" if tail_path else "/"
    target = f"{base_url}{normalized_path}"
    query = urlencode(list(query_items), doseq=True)
    if query:
        return f"{target}?{query}"
    return target


def _filter_request_headers(headers: httpx.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP or lk in {"host", "content-length"}:
            continue
        out[key] = value
    return out


def _rewrite_location(value: str, platform: str, base_url: str) -> str:
    parsed = urlparse(value)
    base = urlparse(base_url)
    prefix = f"/embed/{platform}"
    if parsed.scheme and parsed.netloc:
        if parsed.netloc == base.netloc:
            path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
            return f"{prefix}{path}" + (f"?{parsed.query}" if parsed.query else "")
        return value
    if value.startswith("/"):
        return f"{prefix}{value}"
    return value


def _rewrite_set_cookie(value: str, platform: str) -> str:
    segments = [x.strip() for x in value.split(";")]
    if not segments:
        return value
    out: list[str] = [segments[0]]
    seen_path = False
    for item in segments[1:]:
        if item.lower().startswith("domain="):
            continue
        if item.lower().startswith("path="):
            out.append(f"Path=/embed/{platform}")
            seen_path = True
            continue
        out.append(item)
    if not seen_path:
        out.append(f"Path=/embed/{platform}")
    return "; ".join(out)


def _rewrite_csp(value: str) -> str:
    parts = [x.strip() for x in value.split(";") if x.strip()]
    replaced = False
    out: list[str] = []
    for part in parts:
        if part.lower().startswith("frame-ancestors"):
            out.append("frame-ancestors 'self'")
            replaced = True
        else:
            out.append(part)
    if not replaced:
        out.append("frame-ancestors 'self'")
    return "; ".join(out)


def _copy_response_headers(
    upstream_headers: httpx.Headers, response: StarletteResponse, platform: str, base_url: str
) -> None:
    for key, value in upstream_headers.multi_items():
        lk = key.lower()
        if lk in _HOP_BY_HOP or lk in {"content-length"}:
            continue
        if lk == "x-frame-options":
            continue
        if lk == "content-security-policy":
            response.headers.append(key, _rewrite_csp(value))
            continue
        if lk == "location":
            response.headers.append(key, _rewrite_location(value, platform, base_url))
            continue
        if lk == "set-cookie":
            response.headers.append(key, _rewrite_set_cookie(value, platform))
            continue
        response.headers.append(key, value)


@router.api_route(
    "/{platform}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_http(platform: str, path: str, request: Request) -> Response:
    base = _base_url_for_platform(platform)
    target_url = _build_target_url(base, path, request.query_params.multi_items())
    body = await request.body()
    timeout = httpx.Timeout(60.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=_filter_request_headers(request.headers),
            content=body or None,
        )
    response = Response(content=upstream.content, status_code=upstream.status_code)
    _copy_response_headers(upstream.headers, response, platform, base)
    return response


def _to_ws_url(target_url: str) -> str:
    parsed = urlparse(target_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


@router.websocket("/{platform}/{path:path}")
async def proxy_websocket(platform: str, path: str, websocket: WebSocket) -> None:
    if websockets is None:
        await websocket.close(code=1011)
        return
    settings = get_auth_settings()
    headers_dict = headers_bytes_to_dict(list(websocket.scope.get("headers", [])))
    cookies = parse_cookie_header(headers_dict.get("cookie"))
    token = extract_token_from_websocket_scope(
        cookies=cookies,
        headers=headers_dict,
        settings=settings,
    )
    if not token:
        await websocket.close(code=1008)
        return
    try:
        parse_session_token(token, settings)
    except Exception:  # noqa: BLE001
        await websocket.close(code=1008)
        return

    base = _base_url_for_platform(platform)
    target_http = _build_target_url(base, path, websocket.query_params.multi_items())
    target_ws = _to_ws_url(target_http)

    upstream_headers = _filter_request_headers(httpx.Headers(headers_dict))
    await websocket.accept()
    try:
        async with websockets.connect(target_ws, additional_headers=upstream_headers) as upstream:  # type: ignore[attr-defined]
            async def from_client() -> None:
                while True:
                    msg: dict[str, Any] = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        try:
                            await upstream.close()
                        except Exception:  # noqa: BLE001
                            pass
                        return
                    text = msg.get("text")
                    if text is not None:
                        await upstream.send(text)
                        continue
                    data = msg.get("bytes")
                    if data is not None:
                        await upstream.send(data)

            async def from_upstream() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(str(message))

            task_client = asyncio.create_task(from_client())
            task_upstream = asyncio.create_task(from_upstream())
            done, pending = await asyncio.wait(
                {task_client, task_upstream},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                try:
                    await task
                except Exception:  # noqa: BLE001
                    pass
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        if websocket.application_state.name == "CONNECTED":
            await websocket.close(code=1011)

