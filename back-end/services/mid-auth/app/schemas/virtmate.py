"""Schemas for `/me/virtmate/*` APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VirtmateGptSovitsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    base_url: str
    endpoint: str | None = None
    text_lang: str | None = None
    prompt_lang: str | None = None
    ref_audio: str | None = None
    prompt_text: str | None = None
    top_k: float | int | None = None
    top_p: float | None = None
    temperature: float | None = None
    speed: float | None = None
    extra_json: dict[str, Any] | None = None


class VirtmateDigitalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    gpt_sovits_prompt: str | None = None
    gpt_sovits_lang: str | None = None
    llm_prompt: str | None = None
    ref_audio_path: str | None = None
    live2d_model_path: str | None = None
    created_at: int | None = None


class VirtmateChatSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="default")
    text: str
    with_tts: bool = True
    stream: bool = True
    model: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None


class VirtmateSessionSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="default")
    tts_engine: str | None = None
    cam_permission: str | None = None
    username: str | None = None
    mate_name: str | None = None
    prompt: str | None = None


class VirtmateTtsPlaybackStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="default")
    is_playing: bool
    mouth_y: float | None = None


class VirtmateGlobalConfigUpdateRequest(BaseModel):
    """ASR / TTS settings used by VirtMate frontend."""

    model_config = ConfigDict(extra="forbid")

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
    tts_gpt_sovits_profiles: list[VirtmateGptSovitsProfile] | None = None
    tts_gpt_sovits_default_profile_id: str | None = None
    tts_gpt_sovits_active_profile_id: str | None = None


class VirtmateChatSendResponse(BaseModel):
    ok: bool
    conversation_id: str
    message: dict[str, Any]
    assistant: dict[str, Any]
    tts_audio_url: str | None = None
    tts_error: str | None = None


class VirtmateProfileUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    gpt_sovits_prompt: str | None = None
    gpt_sovits_lang: str | None = None
    llm_prompt: str | None = None
    ref_audio_path: str | None = None
    live2d_model_path: str | None = None


class VirtmateProfileMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str = Field(description="forward/backward")


class VirtmateProfileAssetDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str

