from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.core.security import generate_session_id, hash_password, verify_password
from app.models.provision_logs import ProvisionLog
from app.models.sessions import UserSession
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.services.provision_service import ProvisionError, ProvisionService


def _normalize(value: str) -> str:
    return value.strip().lower()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _integrity_err_text(exc: IntegrityError) -> str:
    return str(getattr(exc, "orig", exc)).lower()


def _is_public_id_conflict(exc: IntegrityError) -> bool:
    t = _integrity_err_text(exc)
    return "uq_users_public_id" in t or "users.public_id" in t


@dataclass
class AuthServiceError(Exception):
    status_code: int
    detail: str


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._provision = ProvisionService()

    def register(
        self,
        db: Session,
        username: str,
        email: str,
        password: str,
        display_name: str | None,
    ) -> User:
        normalized_username = _normalize(username)
        normalized_email = _normalize(email)

        existing = (
            db.query(User)
            .filter(
                or_(
                    User.username == normalized_username,
                    User.email == normalized_email,
                )
            )
            .first()
        )
        if existing is not None:
            raise AuthServiceError(409, "username or email already exists")

        resolved_display_name = (
            display_name if display_name not in (None, "") else normalized_username
        )

        user: User | None = None
        created = False
        for _ in range(10):
            user = User(
                id=str(uuid4()),
                public_id=self._generate_numeric_public_id(db),
                username=normalized_username,
                email=normalized_email,
                password_hash=hash_password(password),
                display_name=resolved_display_name,
                is_active=True,
            )
            db.add(user)
            try:
                db.flush()
                created = True
                break
            except IntegrityError as exc:
                db.rollback()
                if _is_public_id_conflict(exc):
                    continue
                raise AuthServiceError(409, "username or email already exists")
        if user is None or not created:
            raise AuthServiceError(503, "failed to create user")

        try:
            pres = self._provision.provision_user(
                display_name=resolved_display_name,
                username=normalized_username,
                password=password,
            )
        except ProvisionError as exc:
            db.rollback()
            raise AuthServiceError(
                503, f"provisioning failed: {exc}"
            ) from exc

        openwebui_app_uid = str(pres.openwebui_id)
        vocechat_app_uid = str(pres.vocechat_uid)
        memos_app_uid = str(pres.memos_resource_name)
        if self.settings.provision_use_stub:
            # Stub provisioning returns fixed IDs. Keep legacy values for the first user
            # to preserve existing behavior, and only derive unique IDs on conflict.
            if (
                db.query(UserAppMapping)
                .filter(
                    UserAppMapping.app_name == "openwebui",
                    UserAppMapping.app_uid == openwebui_app_uid,
                )
                .first()
                is not None
            ):
                openwebui_app_uid = f"{openwebui_app_uid}-{normalized_username}"

            if (
                db.query(UserAppMapping)
                .filter(
                    UserAppMapping.app_name == "vocechat",
                    UserAppMapping.app_uid == vocechat_app_uid,
                )
                .first()
                is not None
            ):
                digest = hashlib.sha256(f"vc:{normalized_username}".encode("utf-8")).hexdigest()
                vocechat_numeric_uid = int(digest[:8], 16) % 900_000_000 + 100_000_000
                vocechat_app_uid = str(vocechat_numeric_uid)

            if (
                db.query(UserAppMapping)
                .filter(
                    UserAppMapping.app_name == "memos",
                    UserAppMapping.app_uid == memos_app_uid,
                )
                .first()
                is not None
            ):
                digest = hashlib.sha256(f"mm:{normalized_username}".encode("utf-8")).hexdigest()
                memos_numeric_uid = int(digest[:8], 16) % 900_000_000 + 100_000_000
                memos_app_uid = f"users/{memos_numeric_uid}"

        db.add(
            UserAppMapping(
                user_id=user.id,
                app_name="openwebui",
                app_uid=openwebui_app_uid,
                app_username=pres.openwebui_username,
            )
        )
        db.add(
            UserAppMapping(
                user_id=user.id,
                app_name="vocechat",
                app_uid=vocechat_app_uid,
                app_username=pres.vocechat_username,
            )
        )
        db.add(
            UserAppMapping(
                user_id=user.id,
                app_name="memos",
                app_uid=memos_app_uid,
                app_username=pres.memos_username,
            )
        )
        db.add(
            ProvisionLog(
                user_id=user.id,
                app_name="openwebui",
                status="success",
                message=f"id={pres.openwebui_id}",
            )
        )
        db.add(
            ProvisionLog(
                user_id=user.id,
                app_name="vocechat",
                status="success",
                message=f"uid={pres.vocechat_uid}",
            )
        )
        db.add(
            ProvisionLog(
                user_id=user.id,
                app_name="memos",
                status="success",
                message=f"name={pres.memos_resource_name}",
            )
        )

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if self.settings.provision_use_stub and "uq_user_app_mappings_app_uid" in str(
                getattr(exc, "orig", exc)
            ):
                raise AuthServiceError(
                    503,
                    "provisioning failed: stub app uid conflict, please retry",
                ) from exc
            raise AuthServiceError(409, "username or email already exists")

        db.refresh(user)
        return user

    def _generate_numeric_public_id(
        self,
        db: Session,
        *,
        min_digits: int = 8,
        max_digits: int = 18,
        random_attempts_per_width: int = 64,
    ) -> str:
        for digits in range(min_digits, max_digits + 1):
            lower = 10 ** (digits - 1)
            span = 9 * lower

            for _ in range(random_attempts_per_width):
                candidate = str(lower + secrets.randbelow(span))
                exists = (
                    db.query(User.id).filter(User.public_id == candidate).first()
                    is not None
                )
                if not exists:
                    return candidate

            # Deterministic fallback to guarantee progress even under high collision.
            for value in range(lower, lower + min(100_000, span)):
                candidate = str(value)
                exists = (
                    db.query(User.id).filter(User.public_id == candidate).first()
                    is not None
                )
                if not exists:
                    return candidate

        raise AuthServiceError(503, "failed to allocate public_id")

    def login(
        self,
        db: Session,
        identifier: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> tuple[User, UserSession]:
        normalized_identifier = _normalize(identifier)
        if "@" in normalized_identifier:
            user = db.query(User).filter(User.email == normalized_identifier).first()
        else:
            user = db.query(User).filter(User.username == normalized_identifier).first()

        if user is None or not verify_password(password, user.password_hash):
            raise AuthServiceError(401, "invalid credentials")
        if not user.is_active:
            raise AuthServiceError(403, "user is disabled")

        now = datetime.now(timezone.utc)
        session = UserSession(
            session_id=generate_session_id(),
            user_id=user.id,
            expires_at=now + timedelta(seconds=self.settings.session_ttl_seconds),
            user_agent=user_agent,
            ip_address=ip_address,
        )

        user.last_login_at = now
        db.add(session)
        db.commit()
        db.refresh(user)
        db.refresh(session)
        return user, session

    def get_user_by_session(self, db: Session, session_id: str | None) -> User:
        if not session_id:
            raise AuthServiceError(401, "unauthenticated")

        session = (
            db.query(UserSession).filter(UserSession.session_id == session_id).first()
        )
        if session is None:
            raise AuthServiceError(401, "invalid session")

        if _as_utc(session.expires_at) <= datetime.now(timezone.utc):
            db.query(UserSession).filter(UserSession.id == session.id).delete()
            db.commit()
            raise AuthServiceError(401, "invalid session")

        user = db.query(User).filter(User.id == session.user_id).first()
        if user is None:
            db.query(UserSession).filter(UserSession.id == session.id).delete()
            db.commit()
            raise AuthServiceError(401, "invalid session")
        if not user.is_active:
            raise AuthServiceError(403, "user is disabled")

        return user

    def logout(self, db: Session, session_id: str | None) -> None:
        if not session_id:
            raise AuthServiceError(401, "unauthenticated")

        session = (
            db.query(UserSession).filter(UserSession.session_id == session_id).first()
        )
        if session is None:
            raise AuthServiceError(401, "invalid session")

        if _as_utc(session.expires_at) <= datetime.now(timezone.utc):
            db.query(UserSession).filter(UserSession.id == session.id).delete()
            db.commit()
            raise AuthServiceError(401, "invalid session")

        db.query(UserSession).filter(UserSession.id == session.id).delete()
        db.commit()

    def change_password(
        self,
        db: Session,
        session_id: str | None,
        old_password: str,
        new_password: str,
    ) -> None:
        user = self.get_user_by_session(db, session_id)
        if not verify_password(old_password, user.password_hash):
            raise AuthServiceError(400, "wrong old password")

        user.password_hash = hash_password(new_password)
        db.query(UserSession).filter(UserSession.user_id == user.id).delete()
        db.commit()
