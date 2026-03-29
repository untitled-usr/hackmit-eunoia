import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session
from open_webui.internal.db import Base, JSONField, get_db, get_db_context
from open_webui.models.users import User, UserModel, UserProfileImageResponse, Users
from open_webui.utils.validate import validate_profile_image_url
from pydantic import BaseModel, field_validator
from sqlalchemy import Boolean, Column, String, Text

log = logging.getLogger(__name__)

####################
# DB MODEL
####################


class Auth(Base):
    __tablename__ = "auth"

    id = Column(String, primary_key=True, unique=True)
    password = Column(Text)
    active = Column(Boolean)


class AuthModel(BaseModel):
    id: str
    password: str
    active: bool = True


####################
# Forms
####################


class Token(BaseModel):
    token: str
    token_type: str


class SigninResponse(Token, UserProfileImageResponse):
    pass


class LdapForm(BaseModel):
    user: str
    password: str


class ProfileImageUrlForm(BaseModel):
    profile_image_url: str


class UpdatePasswordForm(BaseModel):
    password: str
    new_password: str


class SignupForm(BaseModel):
    password: Optional[str] = None
    profile_image_url: Optional[str] = "/user.png"

    @field_validator("profile_image_url")
    @classmethod
    def check_profile_image_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_profile_image_url(v)
        return v


class AddUserForm(SignupForm):
    role: Optional[str] = "pending"
    name: Optional[str] = None


class AuthsTable:
    def insert_new_auth(
        self,
        password: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        oauth: Optional[dict] = None,
        name: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[UserModel]:
        with get_db_context(db) as db:
            log.info("insert_new_auth")

            id = str(uuid.uuid4())
            display_name = (name or "").strip() or id

            auth = AuthModel(
                **{"id": id, "password": password, "active": True}
            )
            result = Auth(**auth.model_dump())
            db.add(result)

            user = Users.insert_new_user(
                id=id,
                name=display_name,
                profile_image_url=profile_image_url,
                role=role,
                username=id,
                oauth=oauth,
                db=db,
            )

            db.commit()
            db.refresh(result)

            if result and user:
                return user
            else:
                return None

    def insert_new_auth_with_id(
        self,
        id: str,
        password: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        oauth: Optional[dict] = None,
        name: Optional[str] = None,
        username: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[UserModel]:
        with get_db_context(db) as db:
            log.info("insert_new_auth_with_id")
            display_name = (name or "").strip() or id
            uname = (username or "").strip() or id

            auth = AuthModel(**{"id": id, "password": password, "active": True})
            result = Auth(**auth.model_dump())
            db.add(result)

            user = Users.insert_new_user(
                id=id,
                name=display_name,
                profile_image_url=profile_image_url,
                role=role,
                username=uname,
                oauth=oauth,
                db=db,
            )

            db.commit()
            db.refresh(result)

            if result and user:
                return user
            return None

    def authenticate_user(
        self, user_id: str, verify_password: callable, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        log.info(f"authenticate_user: {user_id}")

        user = Users.get_user_by_id(user_id, db=db)
        if not user:
            return None

        try:
            with get_db_context(db) as db:
                auth = db.query(Auth).filter_by(id=user.id, active=True).first()
                if auth:
                    if verify_password(auth.password):
                        return user
                    else:
                        return None
                else:
                    return None
        except Exception:
            return None

    def update_user_password_by_id(
        self, id: str, new_password: str, db: Optional[Session] = None
    ) -> bool:
        try:
            with get_db_context(db) as db:
                result = (
                    db.query(Auth).filter_by(id=id).update({"password": new_password})
                )
                db.commit()
                return True if result == 1 else False
        except Exception:
            return False

    def delete_auth_by_id(self, id: str, db: Optional[Session] = None) -> bool:
        try:
            with get_db_context(db) as db:
                # Delete User
                result = Users.delete_user_by_id(id, db=db)

                if result:
                    db.query(Auth).filter_by(id=id).delete()
                    db.commit()

                    return True
                else:
                    return False
        except Exception:
            return False


Auths = AuthsTable()
