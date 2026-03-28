from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from mid_auth_admin.core.auth_session import extract_token_from_request, parse_session_token
from mid_auth_admin.core.auth_settings import get_auth_settings
from mid_auth_admin.routers.auth import router as auth_router
from mid_auth_admin.routers.admin import router as admin_router
from mid_auth_admin.routers.embed_proxy import router as embed_proxy_router
from mid_auth_admin.routers.platform_users import router as platform_users_router

app = FastAPI(
    title="Mid Auth DB Admin",
    version="0.1.0",
    description="Standalone localhost-only admin API for mid-auth database.",
)

_auth_settings = get_auth_settings()
if _auth_settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_auth_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class AdminAuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if path == "/healthz" or path == "/auth/login" or request.method == "OPTIONS":
            return await call_next(request)

        token = extract_token_from_request(request, _auth_settings)
        if not token:
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
        try:
            session = parse_session_token(token, _auth_settings)
        except Exception:  # noqa: BLE001
            return JSONResponse({"detail": "invalid session"}, status_code=401)
        request.state.admin_username = session.subject
        return await call_next(request)


app.add_middleware(AdminAuthGuardMiddleware)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(embed_proxy_router, prefix="/embed", tags=["embed"])
app.include_router(platform_users_router, prefix="/admin", tags=["platform-users"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

