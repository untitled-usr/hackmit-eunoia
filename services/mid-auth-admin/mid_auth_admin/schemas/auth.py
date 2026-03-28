from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    ok: bool = True
    username: str
    expires_in: int


class MeResponse(BaseModel):
    authenticated: bool
    username: str | None = None

