import os
from dataclasses import dataclass


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


@dataclass(frozen=True)
class Settings:
    database_url: str
    db_echo: bool
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int
    db_pool_recycle: int
    session_cookie_name: str
    session_ttl_seconds: int
    session_cookie_secure: bool
    session_cookie_samesite: str
    session_cookie_path: str
    provision_use_stub: bool
    open_webui_base_url: str | None
    vocechat_base_url: str | None
    memos_base_url: str | None
    provision_http_timeout_seconds: int
    memos_http_timeout_seconds: int
    vocechat_http_timeout_seconds: int
    openwebui_http_timeout_seconds: int
    openwebui_stream_connect_timeout_seconds: int
    openwebui_stream_read_timeout_seconds: int
    openwebui_max_upload_bytes: int
    openwebui_default_model_id: str | None
    downstream_acting_uid_header: str
    open_webui_admin_acting_uid: str | None
    vocechat_admin_acting_uid: str | None
    vocechat_allow_create_admin: bool
    vocechat_bot_acting_uid: str | None
    memos_admin_acting_uid: str | None
    vocechat_sse_connect_timeout_seconds: int
    vocechat_sse_read_timeout_seconds: int
    vocechat_sse_redis_url: str | None
    vocechat_sse_redis_lease_seconds: int
    vocechat_sse_redis_key_prefix: str
    vocechat_sse_instance_id: str | None
    cors_origins: tuple[str, ...]
    session_cookie_domain: str | None
    avatar_max_upload_bytes: int
    virtmate_asr_api_base_url: str
    virtmate_asr_api_timeout_seconds: int
    virtmate_tts_audio_dir: str | None


_DEFAULT_DEV_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:5175",
    "http://localhost:5175",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:7920",
    "http://localhost:7920",
    "http://127.0.0.1:7921",
    "http://localhost:7921",
    "http://127.0.0.1:7923",
    "http://localhost:7923",
    "http://127.0.0.1:7924",
    "http://localhost:7924",
    "http://127.0.0.1:7925",
    "http://localhost:7925",
    "http://127.0.0.1:8012",
    "http://localhost:8012",
    "http://127.0.0.1:7922",
    "http://localhost:7922",
)


def _parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    """Comma-separated list. Empty / unset uses loopback dev origins; ``*`` disables CORS middleware."""
    if raw is None or raw.strip() == "":
        return _DEFAULT_DEV_CORS_ORIGINS
    stripped = raw.strip()
    if stripped == "*":
        return ()
    parts = [p.strip() for p in stripped.split(",") if p.strip()]
    return tuple(parts)


def get_settings() -> Settings:
    samesite = os.getenv("MID_AUTH_SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"

    return Settings(
        database_url=os.getenv(
            "MID_AUTH_DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mid_auth",
        ),
        db_echo=_to_bool(os.getenv("MID_AUTH_DB_ECHO"), default=False),
        db_pool_size=_to_int(os.getenv("MID_AUTH_DB_POOL_SIZE"), default=10),
        db_max_overflow=_to_int(os.getenv("MID_AUTH_DB_MAX_OVERFLOW"), default=20),
        db_pool_timeout=_to_int(os.getenv("MID_AUTH_DB_POOL_TIMEOUT"), default=30),
        db_pool_recycle=_to_int(os.getenv("MID_AUTH_DB_POOL_RECYCLE"), default=1800),
        session_cookie_name=os.getenv("MID_AUTH_SESSION_COOKIE_NAME", "mid_auth_session"),
        session_ttl_seconds=_to_int(
            os.getenv("MID_AUTH_SESSION_TTL_SECONDS"), default=60 * 60 * 24 * 14
        ),
        session_cookie_secure=_to_bool(
            os.getenv("MID_AUTH_SESSION_COOKIE_SECURE"), default=False
        ),
        session_cookie_samesite=samesite,
        session_cookie_path=os.getenv("MID_AUTH_SESSION_COOKIE_PATH", "/"),
        provision_use_stub=_to_bool(
            os.getenv("MID_AUTH_PROVISION_USE_STUB"), default=False
        ),
        open_webui_base_url=_optional_str(os.getenv("MID_AUTH_OPEN_WEBUI_BASE_URL")),
        vocechat_base_url=_optional_str(os.getenv("MID_AUTH_VOCECHAT_BASE_URL")),
        memos_base_url=_optional_str(os.getenv("MID_AUTH_MEMOS_BASE_URL")),
        provision_http_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_PROVISION_HTTP_TIMEOUT_SECONDS"), default=30
        ),
        memos_http_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_MEMOS_HTTP_TIMEOUT_SECONDS"), default=30
        ),
        vocechat_http_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_VOCECHAT_HTTP_TIMEOUT_SECONDS"), default=30
        ),
        openwebui_http_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_OPENWEBUI_HTTP_TIMEOUT_SECONDS"), default=120
        ),
        openwebui_stream_connect_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_OPENWEBUI_STREAM_CONNECT_TIMEOUT_SECONDS"), default=30
        ),
        openwebui_stream_read_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_OPENWEBUI_STREAM_READ_TIMEOUT_SECONDS"), default=0
        ),
        openwebui_max_upload_bytes=_to_int(
            os.getenv("MID_AUTH_OPENWEBUI_MAX_UPLOAD_BYTES"), default=100 * 1024 * 1024
        ),
        openwebui_default_model_id=_optional_str(
            os.getenv("MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID")
        ),
        downstream_acting_uid_header=os.getenv(
            "MID_AUTH_DOWNSTREAM_ACTING_UID_HEADER", "X-Acting-Uid"
        ),
        open_webui_admin_acting_uid=_optional_str(
            os.getenv("MID_AUTH_OPEN_WEBUI_ADMIN_ACTING_UID")
        ),
        vocechat_admin_acting_uid=_optional_str(
            os.getenv("MID_AUTH_VOCECHAT_ADMIN_ACTING_UID")
        ),
        vocechat_allow_create_admin=_to_bool(
            os.getenv("MID_AUTH_VC_ALLOW_CREATE_ADMIN"), default=False
        ),
        vocechat_bot_acting_uid=_optional_str(
            os.getenv("MID_AUTH_VOCECHAT_BOT_ACTING_UID")
        ),
        memos_admin_acting_uid=_optional_str(
            os.getenv("MID_AUTH_MEMOS_ADMIN_ACTING_UID")
        ),
        vocechat_sse_connect_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_VOCECHAT_SSE_CONNECT_TIMEOUT_SECONDS"), default=15
        ),
        vocechat_sse_read_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_VOCECHAT_SSE_READ_TIMEOUT_SECONDS"), default=0
        ),
        vocechat_sse_redis_url=_optional_str(
            os.getenv("MID_AUTH_VOCECHAT_SSE_REDIS_URL")
        ),
        vocechat_sse_redis_lease_seconds=_to_int(
            os.getenv("MID_AUTH_VOCECHAT_SSE_REDIS_LEASE_SECONDS"), default=120
        ),
        vocechat_sse_redis_key_prefix=(
            os.getenv(
                "MID_AUTH_VOCECHAT_SSE_REDIS_KEY_PREFIX", "midauth:vc_sse"
            ).strip()
            or "midauth:vc_sse"
        ),
        vocechat_sse_instance_id=_optional_str(
            os.getenv("MID_AUTH_VOCECHAT_SSE_INSTANCE_ID")
        ),
        cors_origins=_parse_cors_origins(os.getenv("MID_AUTH_CORS_ORIGINS")),
        session_cookie_domain=_optional_str(
            os.getenv("MID_AUTH_SESSION_COOKIE_DOMAIN")
        ),
        avatar_max_upload_bytes=_to_int(
            os.getenv("MID_AUTH_AVATAR_MAX_UPLOAD_BYTES"), default=2 * 1024 * 1024
        ),
        virtmate_asr_api_base_url=os.getenv(
            "MID_AUTH_VIRTMATE_ASR_API_BASE_URL", "http://127.0.0.1:5264"
        ).strip().rstrip("/"),
        virtmate_asr_api_timeout_seconds=_to_int(
            os.getenv("MID_AUTH_VIRTMATE_ASR_API_TIMEOUT_SECONDS"), default=120
        ),
        virtmate_tts_audio_dir=_optional_str(
            os.getenv("MID_AUTH_VIRTMATE_TTS_AUDIO_DIR")
        ),
    )
