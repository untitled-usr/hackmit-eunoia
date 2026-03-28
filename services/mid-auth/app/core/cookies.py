from typing import Any

from fastapi import Response

from app.core.settings import get_settings


def set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    kwargs: dict[str, Any] = dict(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.set_cookie(**kwargs)


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    kwargs: dict[str, Any] = dict(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
    )
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.delete_cookie(**kwargs)
