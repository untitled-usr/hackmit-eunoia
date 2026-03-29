"""Ensure the single built-in system administrator exists (fixed UUID)."""
import logging
import secrets

from open_webui.constants import (
    SYSTEM_ADMIN_USER_ID,
    SYSTEM_ADMIN_USERNAME,
)
from open_webui.models.auths import Auths
from open_webui.models.users import Users
from open_webui.utils.auth import get_password_hash

log = logging.getLogger(__name__)


def ensure_system_admin(db=None) -> None:
    """If no user has role admin, create the system admin with fixed id and username."""
    if Users.has_any_admin(db=db):
        return
    if Users.get_user_by_id(SYSTEM_ADMIN_USER_ID, db=db):
        log.error(
            "Row id=%s exists but no admin user in DB; wipe user/auth tables or fix roles.",
            SYSTEM_ADMIN_USER_ID,
        )
        return
    hashed = get_password_hash(secrets.token_urlsafe(32))
    user = Auths.insert_new_auth_with_id(
        SYSTEM_ADMIN_USER_ID,
        hashed,
        "/user.png",
        "admin",
        name="admin",
        username=SYSTEM_ADMIN_USERNAME,
        db=db,
    )
    if user:
        log.info("Created system admin user id=%s", SYSTEM_ADMIN_USER_ID)
    else:
        log.error("Failed to create system admin user")
