"""Current-user Open WebUI prompts BFF; primary paths ``/me/ai/workbench/prompts*``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.models.users import User
from app.services.openwebui_prompts_service import (
    OpenWebUIPromptsServiceError,
    delete_prompt,
    get_prompt_by_command,
    get_prompt_by_id,
    list_prompts_page,
    list_prompts_simple,
    update_prompt,
)

router = APIRouter()


def _handle(exc: OpenWebUIPromptsServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def list_my_openwebui_prompts_page(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    query: str | None = Query(default=None),
    view_option: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
) -> Any:
    try:
        return list_prompts_page(
            db,
            current_user,
            ow,
            query=query,
            view_option=view_option,
            tag=tag,
            order_by=order_by,
            direction=direction,
            page=page,
        )
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)


def get_my_openwebui_prompt_by_command(
    command: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_prompt_by_command(db, current_user, ow, command)
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)


def list_my_openwebui_prompts(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return list_prompts_simple(db, current_user, ow)
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)


def get_my_openwebui_prompt(
    prompt_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_prompt_by_id(db, current_user, ow, prompt_id)
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)


def patch_my_openwebui_prompt(
    prompt_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> Any:
    try:
        return update_prompt(db, current_user, ow, prompt_id, body)
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)


def delete_my_openwebui_prompt(
    prompt_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    try:
        ok = delete_prompt(db, current_user, ow, prompt_id)
    except OpenWebUIPromptsServiceError as exc:
        _handle(exc)
    if not ok:
        raise HTTPException(status_code=503, detail="openwebui upstream error") from None
    return Response(status_code=204)


register_workbench_route(
    router,
    "/prompts/list",
    list_my_openwebui_prompts_page,
    methods=["GET"],
    response_model=None,
    summary="Open WebUI Prompts 分页列表",
    description=(
        "GET JSON：与下游分页搜索语义一致；可选查询参数 "
        "``query``、``view_option``、``tag``、``order_by``、``direction``、``page``（≥1）。"
        "需 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_prompts_list_page",
)
register_workbench_route(
    router,
    "/prompts/by-command/{command}",
    get_my_openwebui_prompt_by_command,
    methods=["GET"],
    response_model=None,
    summary="按 command 查询 Prompt",
    description=(
        "GET JSON：单条 prompt（含 ``write_access`` 等字段）。"
        "路径参数 ``command`` 为下游存储的 command 字符串（将正确 URL 编码后转发）。"
    ),
    operation_id="me_ai_workbench_openwebui_prompt_by_command",
)
register_workbench_route(
    router,
    "/prompts",
    list_my_openwebui_prompts,
    methods=["GET"],
    response_model=None,
    summary="Open WebUI Prompts 可读全量列表",
    description=(
        "GET JSON：当前用户在下游可见的 prompts 数组（形状与 Open Web UI 一致）。"
        "需 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_prompts_list",
)
register_workbench_route(
    router,
    "/prompts/{prompt_id}",
    get_my_openwebui_prompt,
    methods=["GET"],
    response_model=None,
    summary="Open WebUI Prompt 详情（按 id）",
    description="GET JSON：单条 prompt。无读权限或不存在时 404。",
    operation_id="me_ai_workbench_openwebui_prompt_get",
)
register_workbench_route(
    router,
    "/prompts/{prompt_id}",
    patch_my_openwebui_prompt,
    methods=["PATCH"],
    response_model=None,
    summary="更新 Open WebUI Prompt",
    description=(
        "请求体为 Open Web UI ``PromptForm`` 形状 JSON（如 ``command``、``name``、``content`` 等）；"
        "平台使用 PATCH，下游为 POST update。无写权限时下游 401/403，本平台映射为 404/403。"
    ),
    operation_id="me_ai_workbench_openwebui_prompt_patch",
)
register_workbench_route(
    router,
    "/prompts/{prompt_id}",
    delete_my_openwebui_prompt,
    methods=["DELETE"],
    status_code=204,
    response_class=Response,
    summary="删除 Open WebUI Prompt",
    description="成功时 **204** 无正文；无权限或不存在时 404/403。",
    operation_id="me_ai_workbench_openwebui_prompt_delete",
)
