from pydantic import BaseModel, ConfigDict, Field


class ProfileResponse(BaseModel):
    id: str
    public_id: str
    username: str
    email: str
    display_name: str
    avatar_source: str | None
    avatar_url: str | None
    gender: str | None = None
    description: str | None = None


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    gender: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=512)
