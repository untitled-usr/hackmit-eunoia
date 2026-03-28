from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import get_db
from app.models.users import User
from app.services.auth_service import AuthService, AuthServiceError

auth_service = AuthService()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    cookie_name = get_settings().session_cookie_name
    session_id = request.cookies.get(cookie_name)
    try:
        return auth_service.get_user_by_session(db=db, session_id=session_id)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Session cookie if valid; otherwise ``None`` (no HTTP error)."""
    cookie_name = get_settings().session_cookie_name
    session_id = request.cookies.get(cookie_name)
    if not session_id:
        return None
    try:
        return auth_service.get_user_by_session(db=db, session_id=session_id)
    except AuthServiceError:
        return None
