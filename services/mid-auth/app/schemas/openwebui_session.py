"""Platform response for Open WebUI session user (BFF); shape follows downstream JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenWebUISessionUserOut(BaseModel):
    """Read-only view of the current user's Open WebUI session payload."""

    model_config = ConfigDict(extra="allow")

    token: str = ""
    token_type: str = "ActingUid"
    expires_at: int | None = None
    permissions: dict[str, Any] | None = None
    id: str = Field(..., description="Open WebUI user id for the mapped acting user.")
    name: str
    role: str
    profile_image_url: str
    bio: str | None = None
    gender: str | None = None
    date_of_birth: str | None = None
    status_emoji: str | None = None
    status_message: str | None = None
    status_expires_at: int | None = None
