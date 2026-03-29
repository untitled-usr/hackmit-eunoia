from __future__ import annotations

from datetime import datetime
from typing import Any


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_answer(text: str) -> str:
    return text.replace("#", "").replace("*", "").strip()


def maybe_strip_think(text: str, enabled: bool) -> str:
    if not enabled:
        return text
    return text.split("</think>")[-1].strip()


def get_think_filter_flag(more_set: dict[str, Any]) -> bool:
    return str(more_set.get("思维链think过滤(可选项:on/off)", "off")).lower() == "on"

