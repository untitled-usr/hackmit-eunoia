from __future__ import annotations

from pathlib import Path

from server.config import RuntimeConfig
from server.events import EventBus
from server.services.chat_service import ChatService
from server.services.openwebui_service import OpenWebUiService
from server.services.tts_service import TtsService
from server.storage import SessionStore


class AppContext:
    def __init__(self, root_dir: Path) -> None:
        self.runtime = RuntimeConfig.load(root_dir)
        self.store = SessionStore(root_dir / "data" / "db" / "cs_sessions.db")
        self.events = EventBus()
        self.openwebui = OpenWebUiService()

        self.chat = ChatService(self.runtime, self.store, self.openwebui)
        self.tts = TtsService(self.runtime)
