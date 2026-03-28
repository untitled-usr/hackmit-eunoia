"""Open Web UI wide BFF for current user; primary paths ``/me/ai/workbench/*``.

Narrow platform chat CRUD remains ``/me/ai/chats*``. This router covers folders, config,
notes, skills, functions, and OpenAI-style ``chat/completions`` (stream or not).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.lib.openwebui_safe_config import OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS
from app.models.users import User
from app.schemas.openwebui_folder import (
    OpenWebUIFolderCreateRequest,
    OpenWebUIFolderUpdateRequest,
)
from app.schemas.openwebui_session import OpenWebUISessionUserOut
from app.core.settings import get_settings
from app.integrations.openwebui_client import OpenWebUIClientError
from app.services.ai_chat_service import (
    AiChatServiceError,
    map_openwebui_upstream_error,
    resolve_openwebui_acting_uid,
)
from app.services.openwebui_chat_stream_service import (
    OpenWebUIChatCompletionsStreamSession,
    OpenWebUIChatStreamError,
)
from app.services.openwebui_config_service import get_my_openwebui_safe_config
from app.services.openwebui_folder_service import (
    OpenWebUIFolderServiceError,
    create_my_openwebui_folder,
    delete_my_openwebui_folder,
    get_my_openwebui_folder,
    list_my_openwebui_folders,
    update_my_openwebui_folder,
)
from app.services.openwebui_notes_service import (
    get_my_openwebui_note,
    list_my_openwebui_notes,
)
from app.services.openwebui_session_service import get_my_openwebui_session
from app.services.openwebui_skills_functions_service import (
    get_my_function,
    get_my_skill,
    list_my_functions,
    list_my_skills,
)
from app.services import openwebui_me_meta_service as ow_meta

router = APIRouter()


def _folder_http(exc: OpenWebUIFolderServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_my_openwebui_session_user(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OpenWebUISessionUserOut:
    try:
        return get_my_openwebui_session(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_my_openwebui_folders_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    try:
        return list_my_openwebui_folders(db, current_user, ow)
    except OpenWebUIFolderServiceError as exc:
        _folder_http(exc)


def create_my_openwebui_folder_route(
    payload: OpenWebUIFolderCreateRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return create_my_openwebui_folder(
            db,
            current_user,
            ow,
            payload.model_dump(exclude_none=True),
        )
    except OpenWebUIFolderServiceError as exc:
        _folder_http(exc)


def get_my_openwebui_folder_route(
    folder_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return get_my_openwebui_folder(db, current_user, ow, folder_id)
    except OpenWebUIFolderServiceError as exc:
        _folder_http(exc)


def patch_my_openwebui_folder_route(
    folder_id: str,
    payload: OpenWebUIFolderUpdateRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    body = payload.model_dump(exclude_unset=True)
    if not body:
        raise HTTPException(status_code=422, detail="at least one field required")
    try:
        return update_my_openwebui_folder(db, current_user, ow, folder_id, body)
    except OpenWebUIFolderServiceError as exc:
        _folder_http(exc)


def delete_my_openwebui_folder_route(
    folder_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    delete_contents: bool = Query(default=True),
) -> None:
    try:
        delete_my_openwebui_folder(
            db,
            current_user,
            ow,
            folder_id,
            delete_contents=delete_contents,
        )
    except OpenWebUIFolderServiceError as exc:
        _folder_http(exc)


def get_my_openwebui_config_key(
    config_key: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_my_openwebui_safe_config(db, current_user, ow, config_key)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_my_openwebui_notes_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int | None = None,
) -> Any:
    try:
        return list_my_openwebui_notes(db, current_user, ow, page=page)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_my_openwebui_note_route(
    note_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_my_openwebui_note(db, current_user, ow, note_id)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_my_openwebui_skills(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return list_my_skills(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_my_openwebui_skill(
    skill_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_my_skill(db, current_user, ow, skill_id)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_my_openwebui_functions(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return list_my_functions(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_my_openwebui_function(
    function_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return get_my_function(db, current_user, ow, function_id)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


async def post_my_openwebui_chat_completions(
    request: Request,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
):
    try:
        acting_uid = resolve_openwebui_acting_uid(db, current_user)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    if body.get("stream") is True:
        settings = get_settings()
        try:
            session = await OpenWebUIChatCompletionsStreamSession.start(
                request=request,
                settings=settings,
                acting_uid=acting_uid,
                body=body,
            )
        except OpenWebUIChatStreamError as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from None

        return StreamingResponse(
            session.stream_bytes(),
            media_type=session.response_content_type(),
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        return ow.chat_completion(acting_uid, body)
    except OpenWebUIClientError as exc:
        mapped = map_openwebui_upstream_error(exc)
        raise HTTPException(
            status_code=mapped.status_code, detail=mapped.detail
        ) from None


register_workbench_route(
    router,
    "/session",
    get_my_openwebui_session_user,
    methods=["GET"],
    response_model=OpenWebUISessionUserOut,
    summary="当前 Open Web UI 会话用户（工作台）",
    description=(
        "只读：返回当前登录用户在 Open Web UI 侧对应绑定用户（acting uid）的会话用户信息。"
        "需存在 ``user_app_mappings`` 中 ``app_name=openwebui`` 的映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_session",
)
register_workbench_route(
    router,
    "/folders",
    list_my_openwebui_folders_route,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    summary="Open Web UI 文件夹列表",
    description=(
        "当前用户在 Open Web UI 侧的文件夹摘要列表（JSON 数组）。"
        "需存在 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_folders_list",
)
register_workbench_route(
    router,
    "/folders",
    create_my_openwebui_folder_route,
    methods=["POST"],
    status_code=201,
    response_model=dict[str, Any],
    summary="创建 Open Web UI 文件夹",
    description=(
        "请求体 JSON：`name` 必填，可选 `data`、`meta`、`parent_id`。"
        "需存在 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_folders_create",
)
register_workbench_route(
    router,
    "/folders/{folder_id}",
    get_my_openwebui_folder_route,
    methods=["GET"],
    response_model=dict[str, Any],
    summary="获取单个 Open Web UI 文件夹",
    description=(
        "JSON 对象，形状与下游文件夹模型一致。"
        "需存在 ``openwebui`` 映射；否则 404；无权限或不存在时 404。"
    ),
    operation_id="me_ai_workbench_openwebui_folder_get",
)
register_workbench_route(
    router,
    "/folders/{folder_id}",
    patch_my_openwebui_folder_route,
    methods=["PATCH"],
    response_model=dict[str, Any],
    summary="更新 Open Web UI 文件夹",
    description=(
        "请求体 JSON：可选 `name`、`data`、`meta`（至少提供一项）。"
        "需存在 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_folder_patch",
)
register_workbench_route(
    router,
    "/folders/{folder_id}",
    delete_my_openwebui_folder_route,
    methods=["DELETE"],
    status_code=204,
    response_model=None,
    summary="删除 Open Web UI 文件夹",
    description=(
        "可选查询参数 ``delete_contents``（默认 ``true``），语义与 Open Web UI 一致。"
        "需存在 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_folder_delete",
)
register_workbench_route(
    router,
    "/config/{config_key}",
    get_my_openwebui_config_key,
    methods=["GET"],
    summary="安全只读配置（白名单）",
    description=(
        "只读：转发 Open Web UI 的 ``GET /api/v1/configs/{config_key}``，**仅允许白名单** "
        f"``{sorted(OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS)}``。"
        "**不会**代理 ``connections``、``export``/``import``、``tool_servers``、``terminal_servers``、"
        "``code_execution``、``models`` 等含连接信息或密钥的配置；未列入白名单的 ``config_key`` 返回 **404**。"
        "需存在 ``user_app_mappings`` 中 ``app_name=openwebui`` 的映射；否则 404。"
    ),
    response_model=None,
    operation_id="me_ai_workbench_openwebui_config_get",
)
register_workbench_route(
    router,
    "/notes",
    list_my_openwebui_notes_route,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Notes 列表（只读）",
    description=(
        "GET JSON：当前 acting 用户在下游可读的笔记列表（形状与 Open Web UI fork 的 Notes 列表接口一致，含分页项等）。"
        "可选查询参数 ``page``（≥1）与下游语义一致。"
        "需存在 ``user_app_mappings`` 中 ``app_name=openwebui`` 的映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_notes_list",
)
register_workbench_route(
    router,
    "/notes/{note_id}",
    get_my_openwebui_note_route,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Note 详情（只读）",
    description=(
        "GET JSON：单条笔记详情（含 ``write_access`` 等字段，与下游一致）。"
        "映射与错误语义同列表接口。"
    ),
    operation_id="me_ai_workbench_openwebui_note_get",
)
register_workbench_route(
    router,
    "/skills",
    list_my_openwebui_skills,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Skills 列表（只读）",
    description=(
        "GET JSON：下游 Skills 列表（形状与 Open Web UI 一致）。"
        "需存在 ``openwebui`` 映射；否则 404。"
        "若部署未启用 Skills 路由，下游可能 404，本平台透传为 404。"
    ),
    operation_id="me_ai_workbench_openwebui_skills_list",
)
register_workbench_route(
    router,
    "/skills/{skill_id}",
    get_my_openwebui_skill,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Skill 详情（只读）",
    description=(
        "GET JSON：单条 Skill。映射与错误语义同列表接口。"
    ),
    operation_id="me_ai_workbench_openwebui_skill_get",
)
register_workbench_route(
    router,
    "/functions",
    list_my_openwebui_functions,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Functions 列表（只读）",
    description=(
        "GET JSON：下游 Functions 列表。"
        "需存在 ``openwebui`` 映射；否则 404。"
        "若部署未暴露 Functions 模块，下游可能 404。"
    ),
    operation_id="me_ai_workbench_openwebui_functions_list",
)
register_workbench_route(
    router,
    "/functions/{function_id}",
    get_my_openwebui_function,
    methods=["GET"],
    response_model=None,
    summary="Open Web UI Function 详情（只读）",
    description=(
        "GET JSON：单条 Function。映射与错误语义同列表接口。"
    ),
    operation_id="me_ai_workbench_openwebui_function_get",
)
register_workbench_route(
    router,
    "/chat/completions",
    post_my_openwebui_chat_completions,
    methods=["POST"],
    response_model=None,
    summary="Open Web UI chat/completions（流式或非流式）",
    description=(
        "OpenAI 兼容 JSON：``stream: true`` 时透传下游 **SSE/分块** 响应（``text/event-stream`` 等，以实际下游为准）；"
        "否则返回单次 JSON completion。"
        "与 ``POST /me/ai/chats/{id}/messages`` 不同：后者在平台侧合并 Open Web UI chat JSON，本接口**不修改**会话树，仅为直连下游补全。"
        "需存在 ``openwebui`` 映射；否则 404。"
    ),
    operation_id="me_ai_workbench_openwebui_chat_completions",
)


def get_openwebui_version_public(
    ow: OpenWebUIClientDep,
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_version(ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_changelog_public(
    ow: OpenWebUIClientDep,
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_changelog(ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_health_public(
    ow: OpenWebUIClientDep,
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_health(ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_health_db_public(
    ow: OpenWebUIClientDep,
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_health_db(ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_manifest_safe(
    ow: OpenWebUIClientDep,
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_manifest_safe(ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_version_updates_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_version_updates(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_app_config_safe(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_app_config_safe(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_usage_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_usage(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_openwebui_tasks_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_list_tasks(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_tasks_chat_route(
    chat_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_task_chat(db, current_user, ow, chat_id)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def post_openwebui_task_stop_route(
    task_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return ow_meta.ow_stop_task(db, current_user, ow, task_id)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def get_openwebui_audio_config_safe(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_get_audio_config_safe(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def post_openwebui_audio_config_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> Any:
    try:
        return ow_meta.ow_update_audio_config(db, current_user, ow, body)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_openwebui_audio_models_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_list_audio_models(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_openwebui_audio_voices_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_list_audio_voices(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def post_openwebui_audio_speech_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(raw) > 200_000:
        raise HTTPException(status_code=413, detail="payload too large")
    try:
        resp = ow_meta.ow_create_audio_speech(db, current_user, ow, body)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    ct = resp.headers.get("content-type", "audio/mpeg")
    return StreamingResponse(
        resp.iter_bytes(),
        media_type=ct,
        headers={"Cache-Control": "no-store"},
    )


def post_openwebui_audio_transcription_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    language: str | None = Form(None),
) -> dict[str, Any]:
    raw = file.file.read()
    settings = get_settings()
    if len(raw) > settings.openwebui_max_upload_bytes:
        raise HTTPException(status_code=413, detail="audio file too large")
    try:
        return ow_meta.ow_create_audio_transcription(
            db,
            current_user,
            ow,
            file_content=raw,
            filename=file.filename or "audio",
            content_type=file.content_type,
            language=language,
        )
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_openwebui_models_openai_compat_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_list_models_legacy(db, current_user, ow, refresh=refresh)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


def list_openwebui_models_base_openai_compat_route(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return ow_meta.ow_list_models_base_legacy(db, current_user, ow)
    except AiChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


register_workbench_route(
    router,
    "/openwebui/version",
    get_openwebui_version_public,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_version",
)
register_workbench_route(
    router,
    "/openwebui/changelog",
    get_openwebui_changelog_public,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_changelog",
)
register_workbench_route(
    router,
    "/openwebui/health",
    get_openwebui_health_public,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_health",
)
register_workbench_route(
    router,
    "/openwebui/health/db",
    get_openwebui_health_db_public,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_health_db",
)
register_workbench_route(
    router,
    "/openwebui/manifest",
    get_openwebui_manifest_safe,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_manifest",
)
register_workbench_route(
    router,
    "/openwebui/version/updates",
    get_openwebui_version_updates_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_version_updates",
)
register_workbench_route(
    router,
    "/openwebui/app-config",
    get_openwebui_app_config_safe,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_app_config",
)
register_workbench_route(
    router,
    "/openwebui/usage",
    get_openwebui_usage_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_usage",
)
register_workbench_route(
    router,
    "/openwebui/tasks",
    list_openwebui_tasks_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_tasks",
)
register_workbench_route(
    router,
    "/openwebui/tasks/chat/{chat_id}",
    get_openwebui_tasks_chat_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_tasks_chat",
)
register_workbench_route(
    router,
    "/openwebui/tasks/stop/{task_id}",
    post_openwebui_task_stop_route,
    methods=["POST"],
    response_model=None,
    operation_id="me_ai_workbench_openwebui_task_stop",
)
register_workbench_route(
    router,
    "/openwebui/audio/config",
    get_openwebui_audio_config_safe,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_audio_config_get",
)
register_workbench_route(
    router,
    "/openwebui/audio/config",
    post_openwebui_audio_config_route,
    methods=["POST"],
    response_model=None,
    operation_id="me_ai_workbench_openwebui_audio_config_update",
)
register_workbench_route(
    router,
    "/openwebui/audio/models",
    list_openwebui_audio_models_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_audio_models",
)
register_workbench_route(
    router,
    "/openwebui/audio/voices",
    list_openwebui_audio_voices_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_audio_voices",
)
register_workbench_route(
    router,
    "/openwebui/audio/speech",
    post_openwebui_audio_speech_route,
    methods=["POST"],
    response_model=None,
    operation_id="me_ai_workbench_openwebui_audio_speech",
)
register_workbench_route(
    router,
    "/openwebui/audio/transcriptions",
    post_openwebui_audio_transcription_route,
    methods=["POST"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_audio_transcriptions",
)
register_workbench_route(
    router,
    "/openwebui/models/openai-compat",
    list_openwebui_models_openai_compat_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_models_openai_compat",
)
register_workbench_route(
    router,
    "/openwebui/models/base/openai-compat",
    list_openwebui_models_base_openai_compat_route,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_models_base_openai_compat",
)
