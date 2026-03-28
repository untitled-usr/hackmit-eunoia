import secrets

from passlib.context import CryptContext


def _build_password_context() -> CryptContext:
    try:
        context = CryptContext(
            schemes=["argon2"],
            deprecated="auto",
            argon2__type="ID",
        )
        # Validate backend availability once at startup.
        context.hash("argon2-backend-check")
        return context
    except Exception:
        return CryptContext(schemes=["bcrypt"], deprecated="auto")


PASSWORD_CONTEXT = _build_password_context()


def hash_password(password: str) -> str:
    return PASSWORD_CONTEXT.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return PASSWORD_CONTEXT.verify(password, password_hash)


def generate_session_id() -> str:
    return secrets.token_urlsafe(48)
