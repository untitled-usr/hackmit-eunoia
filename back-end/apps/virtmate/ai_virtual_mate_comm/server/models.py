from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatSendRequest(BaseModel):
    session_id: str = Field(default="default")
    text: str
    with_tts: bool = True
    stream: bool = True
    model: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


class SessionSettingsUpdateRequest(BaseModel):
    session_id: str = Field(default="default")
    tts_engine: str | None = None
    cam_permission: str | None = None
    username: str | None = None
    mate_name: str | None = None
    prompt: str | None = None


class TtsSynthesizeRequest(BaseModel):
    session_id: str = Field(default="default")
    text: str
    tts_engine: str | None = None


class TtsPlaybackStateRequest(BaseModel):
    session_id: str = Field(default="default")
    is_playing: bool
    mouth_y: float | None = None


class AsrRecognizeResponse(BaseModel):
    text: str


class EventPayload(BaseModel):
    type: str
    session_id: str
    data: dict[str, Any]


class GlobalConfigUpdateRequest(BaseModel):
    """ASR / TTS only (LLM 已迁至 Open WebUI)."""

    asr_engine: str | None = None
    asr_model: str | None = None
    asr_device: str | None = None
    asr_compute_type: str | None = None
    asr_cuda_device_index: str | None = None
    asr_disable_auto_fallback: str | None = None
    asr_sensitivity: str | None = None
    asr_voiceprint_switch: str | None = None
    asr_voiceprint_threshold: str | None = None
    tts_local_host: str | None = None
    tts_gpt_sovits_port: str | None = None
    tts_cosyvoice_port: str | None = None
    tts_indextts_port: str | None = None
    tts_voxcpm_port: str | None = None
    tts_local_timeout_sec: str | None = None
    tts_fallback_engine: str | None = None
    tts_default_engine: str | None = None
