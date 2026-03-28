"""User directory DTOs (platform ``public_id`` lookup; safe surface only)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class UserDirectoryLookupRequest(BaseModel):
    """Body for ``POST /me/directory/users/lookup`` (platform user id only)."""

    public_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Target user's ``users.public_id`` (same as in ``/auth/me``).",
    )

    @field_validator("public_id")
    @classmethod
    def strip_public_id(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("public_id must not be empty")
        return t


class UserDirectorySearchResult(BaseModel):
    """Subset of profile fields; never includes VoceChat uid or credentials."""

    public_id: str = Field(
        ...,
        description="Target user's platform ``public_id`` (stable opaque id).",
    )
    username: str = Field(
        default="",
        description="Target user's platform ``username``.",
    )
    email: str = Field(
        default="",
        description="Target user's platform ``email``.",
    )
    display_name: str = Field(
        default="",
        description="From mid-auth ``users.display_name`` / ``username`` when linked to VoceChat.",
    )
    in_online: bool = Field(
        default=False,
        description="Reserved; always false for platform-only directory lookup.",
    )


class UserDirectorySearchRequest(BaseModel):
    """Body for ``POST /me/directory/users/search``."""

    keyword: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Search keyword over public_id, username, or email.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum number of users to return.",
    )


class UserDirectorySearchListResponse(BaseModel):
    items: list[UserDirectorySearchResult]
