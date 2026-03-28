from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.users import User
from app.schemas.profile import ProfileResponse


def _sniff_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


@dataclass
class ProfileServiceError(Exception):
    status_code: int
    detail: str


class ProfileService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def to_profile_response(self, user: User) -> ProfileResponse:
        avatar_source = None
        avatar_url = None
        if (
            user.avatar_data
            and user.avatar_mime_type
            and user.avatar_updated_at is not None
        ):
            avatar_source = "mid-auth"
            t = int(user.avatar_updated_at.timestamp())
            avatar_url = f"/me/avatar?t={t}"
        return ProfileResponse(
            id=user.id,
            public_id=user.public_id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            avatar_source=avatar_source,
            avatar_url=avatar_url,
            gender=user.gender,
            description=user.description,
        )

    @staticmethod
    def update_profile(
        db: Session,
        user: User,
        *,
        username: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        gender: str | None = None,
        description: str | None = None,
        fields_set: set[str] | None = None,
    ) -> User:
        changed = False
        fields = fields_set or set()

        if "username" in fields:
            if username is None:
                raise ProfileServiceError(400, "username cannot be null")
            normalized_username = username.strip().lower()
            if not normalized_username:
                raise ProfileServiceError(400, "username cannot be empty")
            if len(normalized_username) > 64:
                raise ProfileServiceError(400, "username is too long")
            if normalized_username != user.username:
                conflict = (
                    db.query(User.id)
                    .filter(User.username == normalized_username, User.id != user.id)
                    .first()
                )
                if conflict is not None:
                    raise ProfileServiceError(409, "username already exists")
                user.username = normalized_username
                changed = True

        if "email" in fields:
            if email is None:
                raise ProfileServiceError(400, "email cannot be null")
            normalized_email = email.strip().lower()
            if not normalized_email:
                raise ProfileServiceError(400, "email cannot be empty")
            if len(normalized_email) > 255:
                raise ProfileServiceError(400, "email is too long")
            if normalized_email != user.email:
                conflict = (
                    db.query(User.id)
                    .filter(User.email == normalized_email, User.id != user.id)
                    .first()
                )
                if conflict is not None:
                    raise ProfileServiceError(409, "email already exists")
                user.email = normalized_email
                changed = True

        if "display_name" in fields:
            if display_name is None:
                raise ProfileServiceError(400, "display_name cannot be null")
            normalized_display_name = display_name.strip()
            if not normalized_display_name:
                raise ProfileServiceError(400, "display_name cannot be empty")
            if len(normalized_display_name) > 64:
                raise ProfileServiceError(400, "display_name is too long")
            if normalized_display_name != user.display_name:
                user.display_name = normalized_display_name
                changed = True

        if "gender" in fields:
            normalized_gender = (gender or "").strip() or None
            if normalized_gender and len(normalized_gender) > 32:
                raise ProfileServiceError(400, "gender is too long")
            if normalized_gender != user.gender:
                user.gender = normalized_gender
                changed = True

        if "description" in fields:
            normalized_description = (description or "").strip() or None
            if normalized_description and len(normalized_description) > 512:
                raise ProfileServiceError(400, "description is too long")
            if normalized_description != user.description:
                user.description = normalized_description
                changed = True

        if not changed:
            return user

        db.commit()
        db.refresh(user)
        return user

    def set_avatar(self, db: Session, user: User, content: bytes) -> None:
        if not content:
            raise ProfileServiceError(400, "empty file")
        max_b = self._settings.avatar_max_upload_bytes
        if len(content) > max_b:
            raise ProfileServiceError(
                413, f"avatar exceeds limit of {max_b} bytes"
            )
        mime = _sniff_image_mime(content)
        if mime is None:
            raise ProfileServiceError(
                415, "only PNG or JPEG images are allowed"
            )
        now = datetime.now(timezone.utc)
        user.avatar_data = content
        user.avatar_mime_type = mime
        user.avatar_updated_at = now
        db.commit()
        db.refresh(user)

    @staticmethod
    def clear_avatar(db: Session, user: User) -> None:
        user.avatar_data = None
        user.avatar_mime_type = None
        user.avatar_updated_at = None
        db.commit()
        db.refresh(user)

    @staticmethod
    def get_avatar_payload(user: User) -> tuple[bytes, str] | None:
        if not user.avatar_data or not user.avatar_mime_type:
            return None
        return user.avatar_data, user.avatar_mime_type
