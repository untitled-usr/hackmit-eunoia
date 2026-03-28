from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.cookies import clear_session_cookie, set_session_cookie
from app.core.settings import get_settings
from app.db.session import get_db
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services.auth_service import AuthService, AuthServiceError
from app.services.profile_service import ProfileService

router = APIRouter()
auth_service = AuthService()
_profile = ProfileService()


def _to_user_response(user) -> AuthUserResponse:
    pr = _profile.to_profile_response(user)
    return AuthUserResponse(
        id=user.id,
        public_id=user.public_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        avatar_url=pr.avatar_url,
    )


def _get_session_id(request: Request) -> str | None:
    cookie_name = get_settings().session_cookie_name
    return request.cookies.get(cookie_name)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    try:
        user = auth_service.register(
            db=db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
        return RegisterResponse(user=_to_user_response(user))
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    try:
        user, session = auth_service.login(
            db=db,
            identifier=payload.identifier,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        set_session_cookie(response, session.session_id)
        return LoginResponse(user=_to_user_response(user))
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        session_id = _get_session_id(request)
        auth_service.logout(db=db, session_id=session_id)
        clear_session_cookie(response)
        return MessageResponse(message="logged out")
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me", response_model=AuthUserResponse)
def me(request: Request, db: Session = Depends(get_db)) -> AuthUserResponse:
    try:
        user = auth_service.get_user_by_session(db=db, session_id=_get_session_id(request))
        return _to_user_response(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        auth_service.change_password(
            db=db,
            session_id=_get_session_id(request),
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
        clear_session_cookie(response)
        return MessageResponse(message="password changed, please login again")
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
