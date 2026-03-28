"""Shared rules for HTTP proxy responses: allowlisted headers only, safe Content-Disposition.

Used by Open WebUI root/BFF proxy and VoceChat resource streaming so clients never receive
``set-cookie``, internal ``Location`` URLs, or hop-by-hop headers from downstream.
"""

from __future__ import annotations

from collections.abc import Mapping

# Headers safe to reflect to browsers for byte/stream proxies (lowercase names).
_PROXY_RESPONSE_HEADER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "accept-ranges",
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-length",
        "content-range",
        "content-type",
        "etag",
        "expires",
        "last-modified",
        "pragma",
        "vary",
    }
)

_HOP_BY_HOP_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def is_safe_content_disposition_value(value: str) -> bool:
    """Reject ``Content-Disposition`` values that may embed paths or URLs."""
    if "://" in value:
        return False
    if "filename*=" in value.lower():
        return False
    lower = value.lower()
    search_from = 0
    while True:
        pos = lower.find("filename=", search_from)
        if pos < 0:
            break
        rest = value[pos + len("filename=") :].lstrip()
        if rest.startswith('"'):
            end = rest.find('"', 1)
            fn = rest[1:end] if end > 0 else rest[1:]
        else:
            semi = rest.find(";")
            fn = rest[: len(rest) if semi < 0 else semi].strip().strip('"')
        if "/" in fn or "\\" in fn or fn.startswith(".."):
            return False
        search_from = pos + 1
    return True


def filter_allowlisted_proxy_response_headers(
    headers: Mapping[str, str],
) -> dict[str, str]:
    """Return only allowlisted response headers; drop hop-by-hop, cookies, ``Location``, etc."""
    out: dict[str, str] = {}
    for name, value in headers.items():
        ln = name.lower()
        if ln in _HOP_BY_HOP_RESPONSE_HEADERS:
            continue
        if ln not in _PROXY_RESPONSE_HEADER_ALLOWLIST:
            continue
        if ln == "content-disposition" and not is_safe_content_disposition_value(value):
            continue
        out[name] = value
    return out
