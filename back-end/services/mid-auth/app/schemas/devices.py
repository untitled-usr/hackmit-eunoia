"""Platform device session list API DTOs (chat backend; opaque ids only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserDeviceOut(BaseModel):
    device_id: str = Field(..., min_length=1)


class UserDeviceListResponse(BaseModel):
    items: list[UserDeviceOut]


class PushTokenUpdate(BaseModel):
    """FCM (or compatible) push token for one device key."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(
        ...,
        min_length=1,
        description="Client device identifier (VoceChat device key).",
    )
    token: str = Field(
        ...,
        min_length=1,
        description="Push provider token for this device.",
    )
