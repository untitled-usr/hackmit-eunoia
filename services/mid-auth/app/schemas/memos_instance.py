"""Memos InstanceSetting projection for mid-auth BFF (camelCase from downstream)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemosInstanceSettingOut(BaseModel):
    """Instance setting resource returned by Memos; extra keys dropped for stability."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(
        default=None,
        description="Logical resource name, format instance/settings/{segment}.",
    )
    general_setting: dict[str, Any] | None = Field(
        default=None, validation_alias="generalSetting"
    )
    storage_setting: dict[str, Any] | None = Field(
        default=None, validation_alias="storageSetting"
    )
    memo_related_setting: dict[str, Any] | None = Field(
        default=None, validation_alias="memoRelatedSetting"
    )
