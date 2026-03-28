"""Proxy Open Web UI paths expected at the same origin as mid-auth (forked Open Web UI frontend)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user, get_current_user_optional
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.db.session import get_db
from app.models.users import User
from app.services.openwebui_root_proxy_service import run_proxy

router = APIRouter()

# OPTIONS is handled by CORSMiddleware. Register each method with a distinct OpenAPI operation_id.
_PROXY_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _register_proxy(
    path: str,
    downstream_path_fn: Callable[..., str],
    *,
    op_id_prefix: str,
    summary: str,
    tail_param: bool,
    allow_anonymous_mid_auth_user: bool = False,
) -> None:
    if tail_param:
        if allow_anonymous_mid_auth_user:

            async def _handler(
                request: Request,
                tail: str,
                ow: OpenWebUIClientDep,
                db: Session = Depends(get_db),
                current_user: User | None = Depends(get_current_user_optional),
            ) -> object:
                return await run_proxy(
                    request=request,
                    db=db,
                    user=current_user,
                    ow=ow,
                    downstream_path=downstream_path_fn(tail),
                    require_mid_auth_user=False,
                )

        else:

            async def _handler(
                request: Request,
                tail: str,
                ow: OpenWebUIClientDep,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user),
            ) -> object:
                return await run_proxy(
                    request=request,
                    db=db,
                    user=current_user,
                    ow=ow,
                    downstream_path=downstream_path_fn(tail),
                    require_mid_auth_user=True,
                )

    elif allow_anonymous_mid_auth_user:

        async def _handler(
            request: Request,
            ow: OpenWebUIClientDep,
            db: Session = Depends(get_db),
            current_user: User | None = Depends(get_current_user_optional),
        ) -> object:
            return await run_proxy(
                request=request,
                db=db,
                user=current_user,
                ow=ow,
                downstream_path=downstream_path_fn(),
                require_mid_auth_user=False,
            )

    else:

        async def _handler(
            request: Request,
            ow: OpenWebUIClientDep,
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user),
        ) -> object:
            return await run_proxy(
                request=request,
                db=db,
                user=current_user,
                ow=ow,
                downstream_path=downstream_path_fn(),
                require_mid_auth_user=True,
            )

    handler: Callable[..., Awaitable[object]] = _handler
    for method in _PROXY_METHODS:
        router.add_api_route(
            path,
            handler,
            methods=[method],
            operation_id=f"{op_id_prefix}_{method.lower()}",
            summary=summary,
        )


_register_proxy(
    "/api/config",
    lambda: "/api/config",
    op_id_prefix="openwebui_proxy_api_config",
    summary="Proxy /api/config to Open Web UI (optional mid-auth session for acting uid)",
    tail_param=False,
    allow_anonymous_mid_auth_user=True,
)
_register_proxy(
    "/api/config/{tail:path}",
    lambda tail: f"/api/config/{tail}",
    op_id_prefix="openwebui_proxy_api_config_subpath",
    summary="Proxy /api/config/* to Open Web UI (optional mid-auth session)",
    tail_param=True,
    allow_anonymous_mid_auth_user=True,
)
_register_proxy(
    "/me/ai/configs/{tail:path}",
    lambda tail: f"/api/v1/configs/{tail}",
    op_id_prefix="openwebui_proxy_me_ai_configs",
    summary="Proxy /me/ai/configs/* to Open Web UI /api/v1/configs/*",
    tail_param=True,
)
_register_proxy(
    "/ollama/{tail:path}",
    lambda tail: f"/ollama/{tail}",
    op_id_prefix="openwebui_proxy_ollama",
    summary="Proxy /ollama/* to Open Web UI",
    tail_param=True,
)
_register_proxy(
    "/openai/{tail:path}",
    lambda tail: f"/openai/{tail}",
    op_id_prefix="openwebui_proxy_openai",
    summary="Proxy /openai/* to Open Web UI",
    tail_param=True,
)
