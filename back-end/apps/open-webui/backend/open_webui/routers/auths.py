import datetime
import logging
import secrets
from typing import Optional

from open_webui.models.auths import (
    AddUserForm,
    Auths,
    SigninResponse,
)
from open_webui.models.users import (
    UserProfileImageResponse,
    Users,
    UpdateProfileForm,
    UserStatus,
)

from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from open_webui.utils.auth import (
    validate_password,
    get_admin_user,
    get_verified_user,
    get_current_user,
    get_password_hash,
)
from open_webui.internal.db import get_session
from sqlalchemy.orm import Session
from open_webui.utils.access_control import get_permissions
from open_webui.utils.groups import apply_default_group_assignment

router = APIRouter()

log = logging.getLogger(__name__)


############################
# Public register (never assigns admin; system admin is created at startup)
############################


class PublicRegisterForm(BaseModel):
    profile_image_url: Optional[str] = "/user.png"


@router.post("/register", response_model=SigninResponse)
async def register_public(
    request: Request,
    form_data: Optional[PublicRegisterForm] = None,
    db: Session = Depends(get_session),
):
    """
    Unauthenticated registration. New users use DEFAULT_USER_ROLE (never admin).
    DISALLOW_USER_REGISTRATION / ENABLE_SIGNUP apply when any user row exists (including system admin).

    ID-only contract: client does not submit username/name/email/password.
    """
    has_any = Users.has_users(db=db)
    if has_any and request.app.state.config.DISALLOW_USER_REGISTRATION:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="User registration is not allowed",
        )

    if has_any and not request.app.state.config.ENABLE_SIGNUP:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Sign up is disabled",
        )

    role = request.app.state.config.DEFAULT_USER_ROLE
    if role not in {"pending", "user", "admin"}:
        role = "user"
    if role == "admin":
        role = "user"
    # Pending users see a full-screen "activation" overlay and cannot use the app; Memos-style
    # public signup should create accounts that pass the UI role check (user | admin).
    if has_any and role == "pending":
        role = "user"

    profile_image_url = (
        form_data.profile_image_url if form_data and form_data.profile_image_url else "/user.png"
    )
    hashed = get_password_hash(secrets.token_urlsafe(32))

    try:
        new_user = Auths.insert_new_auth(
            hashed,
            profile_image_url,
            role,
            db=db,
        )
        if new_user:
            apply_default_group_assignment(
                request.app.state.config.DEFAULT_GROUP_ID,
                new_user.id,
                db=db,
            )
            return {
                "token": "",
                "token_type": "ActingUid",
                "id": new_user.id,
                "name": new_user.name,
                "role": new_user.role,
                "profile_image_url": f"/api/v1/users/{new_user.id}/profile/image",
            }
        raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
    except HTTPException:
        raise
    except Exception as err:
        log.error(f"Public register error: {str(err)}")
        raise HTTPException(
            500, detail="An internal error occurred while registering the user.",
        )


############################
# GetSessionUser
############################


class SessionUserResponse(BaseModel):
    token: str = ""
    token_type: str = "ActingUid"
    expires_at: Optional[int] = None
    permissions: Optional[dict] = None
    id: str
    name: str
    role: str
    profile_image_url: str


class SessionUserInfoResponse(SessionUserResponse, UserStatus):
    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None


@router.get("/", response_model=SessionUserInfoResponse)
async def get_session_user(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_session),
):
    user_permissions = get_permissions(
        user.id, request.app.state.config.USER_PERMISSIONS, db=db
    )

    return {
        "token": "",
        "token_type": "ActingUid",
        "expires_at": None,
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "profile_image_url": user.profile_image_url,
        "bio": user.bio,
        "gender": user.gender,
        "date_of_birth": user.date_of_birth,
        "status_emoji": user.status_emoji,
        "status_message": user.status_message,
        "status_expires_at": user.status_expires_at,
        "permissions": user_permissions,
    }


############################
# Update Profile
############################


@router.post("/update/profile", response_model=UserProfileImageResponse)
async def update_profile(
    form_data: UpdateProfileForm,
    session_user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if session_user:
        user = Users.update_user_by_id(
            session_user.id,
            form_data.model_dump(),
            db=db,
        )
        if user:
            return user
        else:
            raise HTTPException(400, detail=ERROR_MESSAGES.DEFAULT())
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# Update Timezone
############################


class UpdateTimezoneForm(BaseModel):
    timezone: str


@router.post("/update/timezone")
async def update_timezone(
    form_data: UpdateTimezoneForm,
    session_user=Depends(get_current_user),
    db: Session = Depends(get_session),
):
    if session_user:
        Users.update_user_by_id(
            session_user.id,
            {"timezone": form_data.timezone},
            db=db,
        )
        return {"status": True}
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# AddUser
############################


@router.post("/add", response_model=SigninResponse)
async def add_user(
    request: Request,
    form_data: AddUserForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    requested_role = form_data.role or "pending"
    if requested_role == "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ADMIN_ROLE_NOT_ASSIGNABLE,
        )
    try:
        password = (form_data.password or "").strip()
        if password:
            try:
                validate_password(password)
            except Exception as e:
                raise HTTPException(400, detail=str(e))
            hashed = get_password_hash(password)
        else:
            hashed = get_password_hash(secrets.token_urlsafe(32))

        display_name = (form_data.name or "").strip() or None
        new_user = Auths.insert_new_auth(
            hashed,
            form_data.profile_image_url or "/user.png",
            requested_role,
            name=display_name,
            db=db,
        )

        if new_user:
            apply_default_group_assignment(
                request.app.state.config.DEFAULT_GROUP_ID,
                new_user.id,
                db=db,
            )

            return {
                "token": "",
                "token_type": "ActingUid",
                "id": new_user.id,
                "name": new_user.name,
                "role": new_user.role,
                "profile_image_url": f"/api/v1/users/{new_user.id}/profile/image",
            }
        else:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
    except HTTPException:
        raise
    except Exception as err:
        log.error(f"Add user error: {str(err)}")
        raise HTTPException(
            500, detail="An internal error occurred while adding the user."
        )


############################
# GetAdminDetails
############################


@router.get("/admin/details")
async def get_admin_details(
    request: Request, user=Depends(get_current_user), db: Session = Depends(get_session)
):
    if request.app.state.config.SHOW_ADMIN_DETAILS:
        admin = Users.get_system_admin_user(db=db)
        admin_name = admin.name if admin else None
        admin_id = admin.id if admin else None

        return {
            "id": admin_id,
            "name": admin_name,
        }
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.ACTION_PROHIBITED)


############################
# ToggleSignUp / Admin Config
############################


@router.get("/admin/config")
async def get_admin_config(request: Request, user=Depends(get_admin_user)):
    default_user_role = request.app.state.config.DEFAULT_USER_ROLE
    if default_user_role == "admin":
        default_user_role = "user"
    return {
        "SHOW_ADMIN_DETAILS": request.app.state.config.SHOW_ADMIN_DETAILS,
        "WEBUI_URL": request.app.state.config.WEBUI_URL,
        "ENABLE_SIGNUP": request.app.state.config.ENABLE_SIGNUP,
        "DISALLOW_USER_REGISTRATION": request.app.state.config.DISALLOW_USER_REGISTRATION,
        "ENABLE_API_KEYS": request.app.state.config.ENABLE_API_KEYS,
        "ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS": request.app.state.config.ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS,
        "API_KEYS_ALLOWED_ENDPOINTS": request.app.state.config.API_KEYS_ALLOWED_ENDPOINTS,
        "DEFAULT_USER_ROLE": default_user_role,
        "DEFAULT_GROUP_ID": request.app.state.config.DEFAULT_GROUP_ID,
        "ENABLE_COMMUNITY_SHARING": request.app.state.config.ENABLE_COMMUNITY_SHARING,
        "ENABLE_MESSAGE_RATING": request.app.state.config.ENABLE_MESSAGE_RATING,
        "ENABLE_FOLDERS": request.app.state.config.ENABLE_FOLDERS,
        "FOLDER_MAX_FILE_COUNT": request.app.state.config.FOLDER_MAX_FILE_COUNT,
        "ENABLE_CHANNELS": request.app.state.config.ENABLE_CHANNELS,
        "ENABLE_MEMORIES": request.app.state.config.ENABLE_MEMORIES,
        "ENABLE_NOTES": request.app.state.config.ENABLE_NOTES,
        "ENABLE_USER_WEBHOOKS": request.app.state.config.ENABLE_USER_WEBHOOKS,
        "ENABLE_USER_STATUS": request.app.state.config.ENABLE_USER_STATUS,
        "PENDING_USER_OVERLAY_TITLE": request.app.state.config.PENDING_USER_OVERLAY_TITLE,
        "PENDING_USER_OVERLAY_CONTENT": request.app.state.config.PENDING_USER_OVERLAY_CONTENT,
        "RESPONSE_WATERMARK": request.app.state.config.RESPONSE_WATERMARK,
    }


class AdminConfig(BaseModel):
    SHOW_ADMIN_DETAILS: bool
    WEBUI_URL: str
    ENABLE_SIGNUP: bool
    DISALLOW_USER_REGISTRATION: bool = False
    ENABLE_API_KEYS: bool
    ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS: bool
    API_KEYS_ALLOWED_ENDPOINTS: str
    DEFAULT_USER_ROLE: str
    DEFAULT_GROUP_ID: str
    ENABLE_COMMUNITY_SHARING: bool
    ENABLE_MESSAGE_RATING: bool
    ENABLE_FOLDERS: bool
    FOLDER_MAX_FILE_COUNT: Optional[int | str] = None
    ENABLE_CHANNELS: bool
    ENABLE_MEMORIES: bool
    ENABLE_NOTES: bool
    ENABLE_USER_WEBHOOKS: bool
    ENABLE_USER_STATUS: bool
    PENDING_USER_OVERLAY_TITLE: Optional[str] = None
    PENDING_USER_OVERLAY_CONTENT: Optional[str] = None
    RESPONSE_WATERMARK: Optional[str] = None


@router.post("/admin/config")
async def update_admin_config(
    request: Request, form_data: AdminConfig, user=Depends(get_admin_user)
):
    request.app.state.config.SHOW_ADMIN_DETAILS = form_data.SHOW_ADMIN_DETAILS
    request.app.state.config.WEBUI_URL = form_data.WEBUI_URL
    request.app.state.config.ENABLE_SIGNUP = form_data.ENABLE_SIGNUP
    request.app.state.config.DISALLOW_USER_REGISTRATION = (
        form_data.DISALLOW_USER_REGISTRATION
    )

    request.app.state.config.ENABLE_API_KEYS = form_data.ENABLE_API_KEYS
    request.app.state.config.ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS = (
        form_data.ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS
    )
    request.app.state.config.API_KEYS_ALLOWED_ENDPOINTS = (
        form_data.API_KEYS_ALLOWED_ENDPOINTS
    )

    request.app.state.config.ENABLE_FOLDERS = form_data.ENABLE_FOLDERS
    request.app.state.config.FOLDER_MAX_FILE_COUNT = (
        int(form_data.FOLDER_MAX_FILE_COUNT) if form_data.FOLDER_MAX_FILE_COUNT else ""
    )
    request.app.state.config.ENABLE_CHANNELS = form_data.ENABLE_CHANNELS
    request.app.state.config.ENABLE_MEMORIES = form_data.ENABLE_MEMORIES
    request.app.state.config.ENABLE_NOTES = form_data.ENABLE_NOTES

    if form_data.DEFAULT_USER_ROLE in ["pending", "user"]:
        request.app.state.config.DEFAULT_USER_ROLE = form_data.DEFAULT_USER_ROLE

    request.app.state.config.DEFAULT_GROUP_ID = form_data.DEFAULT_GROUP_ID

    request.app.state.config.ENABLE_COMMUNITY_SHARING = (
        form_data.ENABLE_COMMUNITY_SHARING
    )
    request.app.state.config.ENABLE_MESSAGE_RATING = form_data.ENABLE_MESSAGE_RATING

    request.app.state.config.ENABLE_USER_WEBHOOKS = form_data.ENABLE_USER_WEBHOOKS
    request.app.state.config.ENABLE_USER_STATUS = form_data.ENABLE_USER_STATUS

    request.app.state.config.PENDING_USER_OVERLAY_TITLE = (
        form_data.PENDING_USER_OVERLAY_TITLE
    )
    request.app.state.config.PENDING_USER_OVERLAY_CONTENT = (
        form_data.PENDING_USER_OVERLAY_CONTENT
    )

    request.app.state.config.RESPONSE_WATERMARK = form_data.RESPONSE_WATERMARK

    return {
        "SHOW_ADMIN_DETAILS": request.app.state.config.SHOW_ADMIN_DETAILS,
        "WEBUI_URL": request.app.state.config.WEBUI_URL,
        "ENABLE_SIGNUP": request.app.state.config.ENABLE_SIGNUP,
        "DISALLOW_USER_REGISTRATION": request.app.state.config.DISALLOW_USER_REGISTRATION,
        "ENABLE_API_KEYS": request.app.state.config.ENABLE_API_KEYS,
        "ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS": request.app.state.config.ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS,
        "API_KEYS_ALLOWED_ENDPOINTS": request.app.state.config.API_KEYS_ALLOWED_ENDPOINTS,
        "DEFAULT_USER_ROLE": request.app.state.config.DEFAULT_USER_ROLE,
        "DEFAULT_GROUP_ID": request.app.state.config.DEFAULT_GROUP_ID,
        "ENABLE_COMMUNITY_SHARING": request.app.state.config.ENABLE_COMMUNITY_SHARING,
        "ENABLE_MESSAGE_RATING": request.app.state.config.ENABLE_MESSAGE_RATING,
        "ENABLE_FOLDERS": request.app.state.config.ENABLE_FOLDERS,
        "FOLDER_MAX_FILE_COUNT": request.app.state.config.FOLDER_MAX_FILE_COUNT,
        "ENABLE_CHANNELS": request.app.state.config.ENABLE_CHANNELS,
        "ENABLE_MEMORIES": request.app.state.config.ENABLE_MEMORIES,
        "ENABLE_NOTES": request.app.state.config.ENABLE_NOTES,
        "ENABLE_USER_WEBHOOKS": request.app.state.config.ENABLE_USER_WEBHOOKS,
        "ENABLE_USER_STATUS": request.app.state.config.ENABLE_USER_STATUS,
        "PENDING_USER_OVERLAY_TITLE": request.app.state.config.PENDING_USER_OVERLAY_TITLE,
        "PENDING_USER_OVERLAY_CONTENT": request.app.state.config.PENDING_USER_OVERLAY_CONTENT,
        "RESPONSE_WATERMARK": request.app.state.config.RESPONSE_WATERMARK,
    }
