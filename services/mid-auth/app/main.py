from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.routers import (
    ai_chats_router,
    auth_router,
    chat_resources_router,
    conversations_router,
    diary_router,
    devices_router,
    drift_bottles_router,
    favorites_router,
    groups_router,
    me_memos_router,
    openwebui_chats_router,
    openwebui_me_router,
    openwebui_memories_router,
    openwebui_models_router,
    openwebui_prompts_router,
    openwebui_root_proxy_router,
    openwebui_tools_router,
    posts_router,
    preferences_router,
    profile_router,
    social_router,
    users_router,
    virtmate_router,
)
from app.core.settings import get_settings

_OPENAPI_TAGS = [
    {
        "name": "conversations",
        "description": (
            "1:1 direct messages (VoceChat-backed). Path parameter ``conversation_id`` in v1 is the "
            "peer VoceChat user id (string), not a platform-owned conversation or thread id; it matches "
            "the ``id`` field on each row from GET /me/conversations."
        ),
    },
    {
        "name": "library",
        "description": (
            "Current user's Memos **account-level** API (stats, global attachments, shortcuts, "
            "settings, webhooks, notifications) under ``/me/library/*``. "
            "Memo **content** CRUD uses ``/me/posts*`` (separate from this surface)."
        ),
    },
    {
        "name": "ai-chats",
        "description": (
            "Platform **primary chat** narrow API under ``/me/ai/chats*`` (list, title, messages, "
            "non-stream completion merged into Open WebUI chat JSON, delete). "
            "Does not include the Open WebUI workbench-wide BFF surface."
        ),
    },
    {
        "name": "ai-workbench",
        "description": (
            "Open WebUI **workbench-wide** BFF under ``/me/ai/workbench*`` (models, tools, prompts, "
            "memories, folders, ``chat/completions``, extra ``chats/*`` search/pin/archive/tags, etc.). "
            "Complements ``/me/ai/chats*``; it is not a duplicate of the narrow chat API."
        ),
    },
    {
        "name": "virtmate",
        "description": (
            "VirtMate frontend BFF under ``/me/virtmate*`` (session settings, runtime/global config, "
            "chat send + websocket events, ASR recognize, TTS playback, scene mouth-y). "
            "OpenWebUI user identity is derived from current mid-auth session mapping."
        ),
    },
]

app = FastAPI(
    title="DevStack Mid Auth",
    version="0.1.0",
    openapi_tags=_OPENAPI_TAGS,
)

_settings = get_settings()
if _settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(profile_router, tags=["profile"])
app.include_router(posts_router, tags=["posts"])
app.include_router(diary_router, tags=["posts"])
app.include_router(drift_bottles_router, tags=["posts"])
app.include_router(me_memos_router, tags=["library"])
app.include_router(conversations_router, tags=["conversations"])
app.include_router(chat_resources_router, tags=["chat-resources"])
app.include_router(favorites_router, tags=["favorites"])
app.include_router(social_router, tags=["social"])
app.include_router(users_router, tags=["users"])
app.include_router(preferences_router, tags=["preferences"])
app.include_router(devices_router, tags=["devices"])
app.include_router(groups_router, tags=["groups"])
app.include_router(ai_chats_router, tags=["ai-chats"])
app.include_router(openwebui_chats_router, tags=["ai-workbench"])
app.include_router(openwebui_models_router, tags=["ai-workbench"])
app.include_router(openwebui_prompts_router, tags=["ai-workbench"])
app.include_router(openwebui_tools_router, tags=["ai-workbench"])
app.include_router(openwebui_me_router, tags=["ai-workbench"])
app.include_router(openwebui_memories_router, tags=["ai-workbench"])
app.include_router(openwebui_root_proxy_router, tags=["openwebui-proxy"])
app.include_router(virtmate_router, tags=["virtmate"])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/capabilities")
def capabilities() -> dict[str, list[str]]:
    return {
        "reserved": [
            "unified-auth",
            "friend-graph",
            "api-aggregation",
            "token-exchange",
        ]
    }
