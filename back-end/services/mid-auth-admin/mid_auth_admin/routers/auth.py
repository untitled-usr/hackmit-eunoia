from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from mid_auth_admin.core.auth_settings import AuthSettings, get_auth_settings
from mid_auth_admin.core.auth_session import (
    clear_session_cookie,
    extract_token_from_request,
    issue_session_token,
    parse_session_token,
    set_session_cookie,
    verify_admin_password,
)
from mid_auth_admin.schemas.auth import LoginRequest, LoginResponse, MeResponse

router = APIRouter()


def _require_session_from_request(request: Request, settings: AuthSettings) -> str:
    token = extract_token_from_request(request, settings)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        session = parse_session_token(token, settings)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session") from exc
    return session.subject


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    settings: AuthSettings = Depends(get_auth_settings),
) -> LoginResponse:
    if payload.username.strip() != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not verify_admin_password(payload.password, settings.admin_password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = issue_session_token(settings.admin_username, settings)
    set_session_cookie(response, token, settings)
    return LoginResponse(username=settings.admin_username, expires_in=settings.session_ttl_seconds)


@router.post("/logout")
def logout(
    response: Response,
    settings: AuthSettings = Depends(get_auth_settings),
) -> dict[str, bool]:
    clear_session_cookie(response, settings)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(
    request: Request,
    settings: AuthSettings = Depends(get_auth_settings),
) -> MeResponse:
    username = _require_session_from_request(request, settings)
    return MeResponse(authenticated=True, username=username)

