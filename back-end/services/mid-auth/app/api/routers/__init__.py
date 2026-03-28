from app.api.routers.ai_chats import router as ai_chats_router
from app.api.routers.auth import router as auth_router
from app.api.routers.chat_resources import router as chat_resources_router
from app.api.routers.conversations import router as conversations_router
from app.api.routers.diary import router as diary_router
from app.api.routers.devices import router as devices_router
from app.api.routers.drift_bottles import router as drift_bottles_router
from app.api.routers.favorites import router as favorites_router
from app.api.routers.groups import router as groups_router
from app.api.routers.me_memos import router as me_memos_router
from app.api.routers.openwebui_chats import router as openwebui_chats_router
from app.api.routers.openwebui_me import router as openwebui_me_router
from app.api.routers.openwebui_memories import router as openwebui_memories_router
from app.api.routers.openwebui_models import router as openwebui_models_router
from app.api.routers.openwebui_prompts import router as openwebui_prompts_router
from app.api.routers.openwebui_root_proxy import router as openwebui_root_proxy_router
from app.api.routers.openwebui_tools import router as openwebui_tools_router
from app.api.routers.posts import router as posts_router
from app.api.routers.preferences import router as preferences_router
from app.api.routers.profile import router as profile_router
from app.api.routers.social import router as social_router
from app.api.routers.users import router as users_router
from app.api.routers.virtmate import router as virtmate_router

__all__ = [
    "ai_chats_router",
    "auth_router",
    "chat_resources_router",
    "conversations_router",
    "diary_router",
    "devices_router",
    "drift_bottles_router",
    "favorites_router",
    "groups_router",
    "me_memos_router",
    "openwebui_chats_router",
    "openwebui_me_router",
    "openwebui_memories_router",
    "openwebui_models_router",
    "openwebui_prompts_router",
    "openwebui_root_proxy_router",
    "openwebui_tools_router",
    "posts_router",
    "preferences_router",
    "profile_router",
    "social_router",
    "users_router",
    "virtmate_router",
]
