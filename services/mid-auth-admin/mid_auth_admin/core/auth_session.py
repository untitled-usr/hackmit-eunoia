from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response

from mid_auth_admin.core.auth_settings import AuthSettings


class AuthSessionError(Exception):
    pass


@dataclass(frozen=True)
class AdminSession:
    subject: str
    iat: int
    exp: int
    jti: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign(signing_input: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(digest)


def issue_session_token(username: str, settings: AuthSettings) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
        "jti": uuid.uuid4().hex,
        "iss": "mid-auth-admin",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    parts = [
        _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
    ]
    signing_input = ".".join(parts).encode("ascii")
    parts.append(_sign(signing_input, settings.session_secret))
    return ".".join(parts)


def parse_session_token(token: str, settings: AuthSettings) -> AdminSession:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthSessionError("invalid token format")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expect_sig = _sign(signing_input, settings.session_secret)
    if not hmac.compare_digest(expect_sig, parts[2]):
        raise AuthSessionError("invalid token signature")

    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthSessionError("invalid token payload") from exc

    if not isinstance(payload, dict):
        raise AuthSessionError("invalid token payload")
    sub = payload.get("sub")
    iat = payload.get("iat")
    exp = payload.get("exp")
    jti = payload.get("jti")
    if not isinstance(sub, str) or not isinstance(iat, int) or not isinstance(exp, int) or not isinstance(jti, str):
        raise AuthSessionError("invalid token claims")
    if int(time.time()) >= exp:
        raise AuthSessionError("token expired")
    return AdminSession(subject=sub, iat=iat, exp=exp, jti=jti)


def verify_admin_password(plain_password: str, password_hash: str) -> bool:
    hashed = password_hash.strip()
    if hashed.startswith("plain$"):
        return hmac.compare_digest(hashed[6:], plain_password)

    if hashed.startswith("sha256$"):
        digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(hashed[7:], digest)

    if hashed.startswith("$2a$") or hashed.startswith("$2b$") or hashed.startswith("$2y$"):
        try:
            import bcrypt  # type: ignore
        except Exception:  # noqa: BLE001
            return False
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:  # noqa: BLE001
            return False

    if hashed.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher  # type: ignore
            from argon2.exceptions import VerifyMismatchError  # type: ignore
        except Exception:  # noqa: BLE001
            return False
        try:
            PasswordHasher().verify(hashed, plain_password)
            return True
        except VerifyMismatchError:
            return False
        except Exception:  # noqa: BLE001
            return False

    return False


def set_session_cookie(response: Response, token: str, settings: AuthSettings) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def extract_token_from_request(request: Request, settings: AuthSettings) -> str | None:
    cookie_value = request.cookies.get(settings.cookie_name)
    if cookie_value:
        return cookie_value
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def extract_token_from_websocket_scope(
    *,
    cookies: dict[str, str],
    headers: dict[str, str],
    settings: AuthSettings,
) -> str | None:
    cookie_value = cookies.get(settings.cookie_name)
    if cookie_value:
        return cookie_value
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def parse_cookie_header(raw_cookie: str | None) -> dict[str, str]:
    if not raw_cookie:
        return {}
    out: dict[str, str] = {}
    for part in raw_cookie.split(";"):
        kv = part.strip()
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def headers_bytes_to_dict(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in headers:
        k = key.decode("latin-1").lower()
        v = val.decode("latin-1")
        if k in out:
            out[k] = f"{out[k]},{v}"
        else:
            out[k] = v
    return out

