from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class AuthUserResponse(BaseModel):
    id: str
    public_id: str
    username: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    avatar_url: str | None = None


class RegisterResponse(BaseModel):
    user: AuthUserResponse


class LoginResponse(BaseModel):
    user: AuthUserResponse


class MessageResponse(BaseModel):
    message: str
