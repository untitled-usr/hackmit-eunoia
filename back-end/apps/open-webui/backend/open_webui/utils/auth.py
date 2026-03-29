import logging
import base64
import hmac
import hashlib
import requests
import os
import bcrypt

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import json

from datetime import datetime
from typing import Optional

from opentelemetry import trace

from open_webui.models.users import Users
from open_webui.models.auths import Auths

from open_webui.constants import ERROR_MESSAGES

from open_webui.env import (
    ENABLE_PASSWORD_VALIDATION,
    LICENSE_BLOB,
    PASSWORD_VALIDATION_HINT,
    PASSWORD_VALIDATION_REGEX_PATTERN,
    pk,
    STATIC_DIR,
    ACTING_USER_ID_HEADER,
)

from fastapi import BackgroundTasks, Depends, HTTPException, Request, Response, status

log = logging.getLogger(__name__)

##############
# Auth Utils
##############


def override_static(path: str, content: str):
    # Ensure path is safe
    if "/" in path or ".." in path:
        log.error(f"Invalid path: {path}")
        return

    file_path = os.path.join(STATIC_DIR, path)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(base64.b64decode(content))  # Convert Base64 back to raw binary


def get_license_data(app, key):
    def data_handler(data):
        for k, v in data.items():
            if k == "resources":
                for p, c in v.items():
                    globals().get("override_static", lambda a, b: None)(p, c)
            elif k == "count":
                setattr(app.state, "USER_COUNT", v)
            elif k == "name":
                setattr(app.state, "WEBUI_NAME", v)
            elif k == "metadata":
                setattr(app.state, "LICENSE_METADATA", v)

    def handler(u):
        res = requests.post(
            f"{u}/api/v1/license/",
            json={"key": key, "version": "1"},
            timeout=5,
        )

        if getattr(res, "ok", False):
            payload = getattr(res, "json", lambda: {})()
            data_handler(payload)
            return True
        else:
            log.error(
                f"License: retrieval issue: {getattr(res, 'text', 'unknown error')}"
            )

    if key:
        us = [
            "https://api.openwebui.com",
            "https://licenses.api.openwebui.com",
        ]
        try:
            for u in us:
                if handler(u):
                    return True
        except Exception as ex:
            log.exception(f"License: Uncaught Exception: {ex}")

    try:
        if LICENSE_BLOB:
            nl = 12
            kb = hashlib.sha256((key.replace("-", "").upper()).encode()).digest()

            def nt(b):
                return b[:nl], b[nl:]

            lb = base64.b64decode(LICENSE_BLOB)
            ln, lt = nt(lb)

            aesgcm = AESGCM(kb)
            p = json.loads(aesgcm.decrypt(ln, lt, None))
            pk.verify(base64.b64decode(p["s"]), p["p"].encode())

            pb = base64.b64decode(p["p"])
            pn, pt = nt(pb)

            data = json.loads(aesgcm.decrypt(pn, pt, None).decode())
            if not data.get("exp") and data.get("exp") < datetime.now().date():
                return False

            data_handler(data)
            return True
    except Exception as e:
        log.error(f"License: {e}")

    return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def validate_password(password: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        raise Exception(
            ERROR_MESSAGES.PASSWORD_TOO_LONG,
        )

    if ENABLE_PASSWORD_VALIDATION:
        if not PASSWORD_VALIDATION_REGEX_PATTERN.match(password):
            raise Exception(ERROR_MESSAGES.INVALID_PASSWORD(PASSWORD_VALIDATION_HINT))

    return True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return (
        bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
        if hashed_password
        else None
    )


def get_user_from_acting_uid_header(request: Request):
    """Resolve the current user from ``ACTING_USER_ID_HEADER`` only (no JWT/session)."""
    acting_uid = (request.headers.get(ACTING_USER_ID_HEADER) or "").strip()
    if not acting_uid:
        return None
    return Users.get_user_by_id(acting_uid)


async def get_current_user(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
):
    acting_uid = (request.headers.get(ACTING_USER_ID_HEADER) or "").strip()
    if not acting_uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = Users.get_user_by_id(acting_uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.INVALID_TOKEN,
        )

    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("client.user.id", user.id)
        current_span.set_attribute("client.user.name", user.name)
        current_span.set_attribute("client.user.role", user.role)
        current_span.set_attribute("client.auth.type", "acting_uid")

    if background_tasks:
        background_tasks.add_task(Users.update_last_active_by_id, user.id)

    return user


def get_verified_user(user=Depends(get_current_user)):
    if user.role not in {"user", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


def get_admin_user(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


def create_admin_user(password: str):
    """
    Ensures the fixed system admin exists (see ensure_system_admin at startup).
    If password is non-empty, sets that password on the system admin (legacy env bootstrap).
    """
    from open_webui.utils.system_admin import ensure_system_admin

    try:
        ensure_system_admin()
        user = Users.get_system_admin_user()
        if not user:
            return None
        if password:
            hashed = get_password_hash(password)
            Auths.update_user_password_by_id(user.id, hashed)
        return user
    except Exception as e:
        log.error(f"Error in create_admin_user: {e}")
        return None
