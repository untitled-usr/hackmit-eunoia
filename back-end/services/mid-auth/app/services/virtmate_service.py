"""VirtMate service layer for `/me/virtmate/*` APIs."""

from __future__ import annotations

import asyncio
import audioop
import base64
import binascii
import hashlib
import json
import shutil
import subprocess
import time
import uuid
import wave
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.models.users import User
from app.models.virtmate import (
    VirtmateSessionMessage,
    VirtmateSessionSettings,
    VirtmateSessionState,
    VirtmateUserGlobal,
)
from app.services.ai_chat_service import (
    AiChatServiceError,
    map_openwebui_upstream_error,
    resolve_openwebui_acting_uid,
)

try:
    import pynvml as nv
except Exception:  # pragma: no cover
    nv = None

try:
    import torch
except Exception:  # pragma: no cover
    torch = None


@dataclass
class VirtmateServiceError(Exception):
    status_code: int
    detail: str


_DEFAULT_SESSION_SETTINGS: dict[str, Any] = {
    "username": "开拓者",
    "mate_name": "小月",
    "prompt": "",
    "tts_engine": "GPT-SoVITS API",
    "cam_permission": "关闭",
}

_DEFAULT_GPT_SOVITS_PROFILE: dict[str, Any] = {
    "id": "default",
    "name": "默认 GPT-SoVITS",
    "base_url": "http://host.docker.internal:9880",
    "endpoint": "/",
    "text_lang": "auto",
    "prompt_lang": "auto",
    "ref_audio": "",
    "prompt_text": "",
    "top_k": 5,
    "top_p": 1.0,
    "temperature": 1.0,
    "speed": 1.0,
    "extra_json": {},
}

_DEFAULT_GLOBAL: dict[str, Any] = {
    "openwebui": {"base_url": "", "user_id_header": "X-Acting-Uid"},
    "asr": {
        "engine": "faster_whisper_cuda",
        "model": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "cuda_device_index": "0",
        "disable_auto_fallback": False,
        "sensitivity": "中",
        "voiceprint_switch": "关闭",
        "voiceprint_threshold": "0.6",
    },
    "tts": {
        "local_host": "127.0.0.1",
        "gpt_sovits_port": "9880",
        "cosyvoice_port": "9881",
        "indextts_port": "9884",
        "voxcpm_port": "9885",
        "local_timeout_sec": "180",
        "fallback_engine": "云端edge-tts",
        "default_engine": "GPT-SoVITS API",
        "gpt_sovits_profiles": [deepcopy(_DEFAULT_GPT_SOVITS_PROFILE)],
        "gpt_sovits_default_profile_id": "default",
        "gpt_sovits_active_profile_id": "default",
    },
}

_BUILTIN_DEFAULT_DIGITAL_PROFILE: dict[str, Any] = {
    "id": "default",
    "title": "默认 Profile",
    "gpt_sovits_prompt": "",
    "gpt_sovits_lang": "auto",
    "llm_prompt": "",
    "ref_audio_path": "",
    "live2d_model_path": "",
    "created_at": 0,
}

_DEFAULT_DIGITAL_PROFILES: dict[str, Any] = {
    "profiles": [],
    "active_profile_id": "default",
    "schema_version": 1,
}

_SESSION_SETTING_ALLOWED = {"tts_engine", "cam_permission", "username", "mate_name", "prompt"}
_GLOBAL_ASR_ALLOWED = {
    "asr_engine",
    "asr_model",
    "asr_device",
    "asr_compute_type",
    "asr_cuda_device_index",
    "asr_disable_auto_fallback",
    "asr_sensitivity",
    "asr_voiceprint_switch",
    "asr_voiceprint_threshold",
}
_GLOBAL_TTS_ALLOWED = {
    "tts_local_host",
    "tts_gpt_sovits_port",
    "tts_cosyvoice_port",
    "tts_indextts_port",
    "tts_voxcpm_port",
    "tts_local_timeout_sec",
    "tts_fallback_engine",
    "tts_default_engine",
    "tts_gpt_sovits_profiles",
    "tts_gpt_sovits_default_profile_id",
    "tts_gpt_sovits_active_profile_id",
}


class VirtmateService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._audio_dir = Path(
            self._settings.virtmate_tts_audio_dir or "/tmp/mid_auth_virtmate_audio"
        )
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        self._profile_assets_dir = self._audio_dir / "profile_assets"
        self._profile_assets_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _event_key(user: User, session_id: str) -> str:
        sid = (session_id or "default").strip() or "default"
        return f"{user.id}:{sid}"

    @staticmethod
    def _safe_json_load(raw: str | None, default: dict[str, Any]) -> dict[str, Any]:
        if not raw:
            return dict(default)
        try:
            data = json.loads(raw)
        except Exception:
            return dict(default)
        if not isinstance(data, dict):
            return dict(default)
        out = dict(default)
        out.update(data)
        return out

    @staticmethod
    def _normalize_endpoint_path(raw_endpoint: Any) -> str:
        endpoint = str(raw_endpoint or "/").strip() or "/"
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        # Normalize `/tts/` -> `/tts`, keep root `/`.
        if endpoint != "/":
            endpoint = endpoint.rstrip("/") or "/"
        return endpoint

    @staticmethod
    def _normalize_gpt_sovits_profile(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        profile_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        base_url = str(raw.get("base_url") or "").strip()
        if not profile_id or not name or not base_url:
            return None
        endpoint = VirtmateService._normalize_endpoint_path(raw.get("endpoint"))
        profile: dict[str, Any] = {
            "id": profile_id,
            "name": name,
            "base_url": base_url.rstrip("/"),
            "endpoint": endpoint,
            "text_lang": str(raw.get("text_lang") or "").strip() or "zh",
            "prompt_lang": str(raw.get("prompt_lang") or "").strip() or "zh",
            "ref_audio": str(raw.get("ref_audio") or "").strip(),
            "prompt_text": str(raw.get("prompt_text") or "").strip(),
            "extra_json": raw.get("extra_json")
            if isinstance(raw.get("extra_json"), dict)
            else {},
        }
        for key in ("top_k", "top_p", "temperature", "speed"):
            value = raw.get(key)
            if value is None or value == "":
                continue
            try:
                profile[key] = float(value)
            except Exception:
                continue
        return profile

    @classmethod
    def _normalize_tts_profiles(cls, tts: dict[str, Any]) -> dict[str, Any]:
        raw_profiles = tts.get("gpt_sovits_profiles")
        profiles: list[dict[str, Any]] = []
        if isinstance(raw_profiles, list):
            for item in raw_profiles:
                profile = cls._normalize_gpt_sovits_profile(item)
                if profile is not None:
                    profiles.append(profile)
        if not profiles:
            profiles = [deepcopy(_DEFAULT_GPT_SOVITS_PROFILE)]
        default_id = str(tts.get("gpt_sovits_default_profile_id") or "").strip()
        active_id = str(tts.get("gpt_sovits_active_profile_id") or "").strip()
        valid_ids = {str(item["id"]) for item in profiles}
        if default_id not in valid_ids:
            default_id = str(profiles[0]["id"])
        if active_id not in valid_ids:
            active_id = default_id
        tts["gpt_sovits_profiles"] = profiles
        tts["gpt_sovits_default_profile_id"] = default_id
        tts["gpt_sovits_active_profile_id"] = active_id
        return tts

    @staticmethod
    def _map_openwebui_error(exc: OpenWebUIClientError) -> VirtmateServiceError:
        mapped = map_openwebui_upstream_error(exc)
        return VirtmateServiceError(mapped.status_code, mapped.detail)

    def _asr_base_url(self) -> str:
        return self._settings.virtmate_asr_api_base_url.rstrip("/")

    def _asr_timeout(self) -> float:
        return float(self._settings.virtmate_asr_api_timeout_seconds)

    def get_global_config(self, db: Session, user: User) -> dict[str, Any]:
        row = (
            db.query(VirtmateUserGlobal)
            .filter(VirtmateUserGlobal.user_id == user.id)
            .first()
        )
        merged = deepcopy(_DEFAULT_GLOBAL)
        if row is not None:
            try:
                payload = json.loads(row.config_json)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key in ("asr", "tts"):
                    section = payload.get(key)
                    if isinstance(section, dict):
                        merged[key].update(section)
        merged["tts"] = self._normalize_tts_profiles(dict(merged["tts"]))
        merged["openwebui"] = {
            "base_url": (self._settings.open_webui_base_url or "").rstrip("/"),
            "user_id_header": self._settings.downstream_acting_uid_header,
        }
        return merged

    def update_global_config(
        self, db: Session, user: User, payload: dict[str, Any]
    ) -> dict[str, Any]:
        current = self.get_global_config(db, user)
        asr = dict(current["asr"])
        tts = dict(current["tts"])

        for key, value in payload.items():
            if value is None:
                continue
            if key in _GLOBAL_ASR_ALLOWED:
                map_key = key.replace("asr_", "")
                if map_key == "disable_auto_fallback":
                    asr[map_key] = str(value).strip() in {"1", "true", "yes", "on", "开启"}
                else:
                    asr[map_key] = value
            elif key in _GLOBAL_TTS_ALLOWED:
                map_key = key.replace("tts_", "")
                tts[map_key] = value
        tts = self._normalize_tts_profiles(tts)

        row = (
            db.query(VirtmateUserGlobal)
            .filter(VirtmateUserGlobal.user_id == user.id)
            .first()
        )
        stored = {"asr": asr, "tts": tts}
        text = json.dumps(stored, ensure_ascii=False)
        if row is None:
            row = VirtmateUserGlobal(user_id=user.id, config_json=text)
            db.add(row)
        else:
            row.config_json = text
        db.commit()
        return self.get_global_config(db, user)

    @staticmethod
    def _normalize_one_digital_profile(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        profile_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not profile_id or not title:
            return None
        created_at_raw = raw.get("created_at")
        try:
            created_at = int(created_at_raw) if created_at_raw is not None else int(time.time())
        except Exception:
            created_at = int(time.time())
        return {
            "id": profile_id,
            "title": title,
            "gpt_sovits_prompt": str(raw.get("gpt_sovits_prompt") or "").strip(),
            "gpt_sovits_lang": str(raw.get("gpt_sovits_lang") or "").strip() or "zh",
            "llm_prompt": str(raw.get("llm_prompt") or "").strip(),
            "ref_audio_path": str(raw.get("ref_audio_path") or "").strip(),
            "live2d_model_path": str(raw.get("live2d_model_path") or "").strip(),
            "created_at": created_at,
        }

    @classmethod
    def _normalize_digital_profiles(cls, raw: Any) -> dict[str, Any]:
        source = raw if isinstance(raw, dict) else {}
        rows = source.get("profiles")
        parsed_profiles: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for item in rows:
                normalized = cls._normalize_one_digital_profile(item)
                if normalized is not None:
                    parsed_profiles.append(normalized)
        stored_default = next(
            (
                p
                for p in parsed_profiles
                if isinstance(p, dict) and str(p.get("id") or "").strip() == "default"
            ),
            None,
        )
        builtin_default = deepcopy(_BUILTIN_DEFAULT_DIGITAL_PROFILE)
        if isinstance(stored_default, dict):
            for key in (
                "title",
                "gpt_sovits_prompt",
                "gpt_sovits_lang",
                "llm_prompt",
                "ref_audio_path",
                "live2d_model_path",
                "created_at",
            ):
                if stored_default.get(key) is not None:
                    builtin_default[key] = stored_default.get(key)
        profiles: list[dict[str, Any]] = [builtin_default]
        for p in parsed_profiles:
            if str(p.get("id") or "").strip() == "default":
                continue
            profiles.append(p)
        active_id = str(source.get("active_profile_id") or "").strip()
        valid_ids = {str(p.get("id") or "").strip() for p in profiles}
        if active_id and active_id not in valid_ids:
            active_id = ""
        if not active_id:
            active_id = "default"
        schema_version = int(source.get("schema_version") or 1)
        return {
            "profiles": profiles,
            "active_profile_id": active_id,
            "schema_version": schema_version,
        }

    def _load_user_global_payload(self, db: Session, user: User) -> tuple[VirtmateUserGlobal | None, dict[str, Any]]:
        row = (
            db.query(VirtmateUserGlobal)
            .filter(VirtmateUserGlobal.user_id == user.id)
            .first()
        )
        if row is None:
            return None, {}
        try:
            payload = json.loads(row.config_json)
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return row, payload

    def _save_user_global_payload(
        self, db: Session, user: User, row: VirtmateUserGlobal | None, payload: dict[str, Any]
    ) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        if row is None:
            row = VirtmateUserGlobal(user_id=user.id, config_json=text)
            db.add(row)
        else:
            row.config_json = text
        db.commit()

    def list_digital_profiles(self, db: Session, user: User) -> dict[str, Any]:
        _row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        return digital

    def create_digital_profile(self, db: Session, user: User, data: dict[str, Any]) -> dict[str, Any]:
        row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        seed = next(
            (p for p in digital["profiles"] if str(p.get("id")) == str(digital.get("active_profile_id"))),
            None,
        ) or deepcopy(_BUILTIN_DEFAULT_DIGITAL_PROFILE)

        def _pick_text(key: str) -> str:
            raw = data.get(key)
            val = str(raw or "").strip()
            if val:
                return val
            return str(seed.get(key) or "").strip()

        title = _pick_text("title") or "默认 Profile"
        item = self._normalize_one_digital_profile(
            {
                "id": uuid.uuid4().hex,
                "title": title,
                "gpt_sovits_prompt": _pick_text("gpt_sovits_prompt"),
                "gpt_sovits_lang": _pick_text("gpt_sovits_lang") or "auto",
                "llm_prompt": _pick_text("llm_prompt"),
                "ref_audio_path": _pick_text("ref_audio_path"),
                "live2d_model_path": _pick_text("live2d_model_path"),
                "created_at": int(time.time()),
            }
        )
        if item is None:
            raise VirtmateServiceError(400, "invalid profile payload")
        digital["profiles"].append(item)
        digital["active_profile_id"] = item["id"]
        payload["digital_profiles"] = digital
        self._save_user_global_payload(db, user, row, payload)
        return item

    def update_digital_profile(
        self, db: Session, user: User, profile_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        target = None
        for item in digital["profiles"]:
            if str(item.get("id")) == profile_id:
                target = item
                break
        if target is None:
            raise VirtmateServiceError(404, "profile not found")
        for key in (
            "title",
            "gpt_sovits_prompt",
            "gpt_sovits_lang",
            "llm_prompt",
            "ref_audio_path",
            "live2d_model_path",
        ):
            if key in updates and updates[key] is not None:
                target[key] = str(updates[key]).strip()
        if not str(target.get("title") or "").strip():
            raise VirtmateServiceError(400, "title is required")
        payload["digital_profiles"] = digital
        self._save_user_global_payload(db, user, row, payload)
        return target

    def delete_digital_profile(self, db: Session, user: User, profile_id: str) -> None:
        row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        next_profiles = [p for p in digital["profiles"] if str(p.get("id")) != profile_id]
        if len(next_profiles) == len(digital["profiles"]):
            raise VirtmateServiceError(404, "profile not found")
        digital["profiles"] = next_profiles
        if digital["active_profile_id"] == profile_id:
            digital["active_profile_id"] = str(next_profiles[0]["id"]) if next_profiles else ""
        payload["digital_profiles"] = digital
        self._save_user_global_payload(db, user, row, payload)

    def activate_digital_profile(self, db: Session, user: User, profile_id: str) -> dict[str, Any]:
        row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        if not any(str(p.get("id")) == profile_id for p in digital["profiles"]):
            raise VirtmateServiceError(404, "profile not found")
        digital["active_profile_id"] = profile_id
        payload["digital_profiles"] = digital
        self._save_user_global_payload(db, user, row, payload)
        return digital

    def move_digital_profile(
        self, db: Session, user: User, profile_id: str, direction: str
    ) -> dict[str, Any]:
        if direction not in {"forward", "backward"}:
            raise VirtmateServiceError(400, "direction must be forward/backward")
        row, payload = self._load_user_global_payload(db, user)
        digital = self._normalize_digital_profiles(payload.get("digital_profiles"))
        profiles = digital["profiles"]
        idx = next((i for i, p in enumerate(profiles) if str(p.get("id")) == profile_id), -1)
        if idx < 0:
            raise VirtmateServiceError(404, "profile not found")
        if direction == "forward" and idx < len(profiles) - 1:
            profiles[idx], profiles[idx + 1] = profiles[idx + 1], profiles[idx]
        elif direction == "backward" and idx > 0:
            profiles[idx], profiles[idx - 1] = profiles[idx - 1], profiles[idx]
        payload["digital_profiles"] = digital
        self._save_user_global_payload(db, user, row, payload)
        return digital

    @staticmethod
    def _safe_asset_name(name: str) -> str:
        base = name.replace("\\", "/").split("/")[-1]
        return "".join(ch for ch in base if ch.isalnum() or ch in {"-", "_", "."}) or "file.bin"

    def save_profile_asset(self, user: User, kind: str, filename: str, content: bytes) -> str:
        if kind not in {"audio", "live2d"}:
            raise VirtmateServiceError(400, "invalid asset kind")
        user_dir = self._profile_assets_dir / str(user.id) / kind
        user_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_asset_name(filename or "upload.bin")
        ext = Path(safe_name).suffix
        final_name = f"{uuid.uuid4().hex}{ext}" if ext else uuid.uuid4().hex
        path = user_dir / final_name
        path.write_bytes(content)
        return f"/me/virtmate/profile-assets/{kind}/{final_name}"

    def get_profile_asset_path(self, user: User, kind: str, filename: str) -> Path:
        if kind not in {"audio", "live2d"}:
            raise VirtmateServiceError(404, "asset not found")
        safe_name = self._safe_asset_name(filename)
        path = self._profile_assets_dir / str(user.id) / kind / safe_name
        if not path.exists():
            raise VirtmateServiceError(404, "asset not found")
        return path

    def delete_profile_asset_by_url(self, user: User, kind: str, path: str) -> None:
        if kind not in {"audio", "live2d"}:
            raise VirtmateServiceError(400, "invalid asset kind")
        raw = str(path or "").strip()
        prefix = f"/me/virtmate/profile-assets/{kind}/"
        if not raw.startswith(prefix):
            raise VirtmateServiceError(400, "invalid asset path")
        safe_name = self._safe_asset_name(raw[len(prefix) :])
        target = self._profile_assets_dir / str(user.id) / kind / safe_name
        if not target.exists():
            raise VirtmateServiceError(404, "asset not found")
        try:
            target.unlink()
        except Exception as exc:
            raise VirtmateServiceError(500, f"failed to delete asset: {exc}") from exc

    def get_session_settings(self, db: Session, user: User, session_id: str) -> dict[str, Any]:
        sid = (session_id or "default").strip() or "default"
        row = (
            db.query(VirtmateSessionSettings)
            .filter(
                VirtmateSessionSettings.user_id == user.id,
                VirtmateSessionSettings.session_id == sid,
            )
            .first()
        )
        if row is None:
            out = dict(_DEFAULT_SESSION_SETTINGS)
            out["tts_engine"] = self.get_global_config(db, user)["tts"]["default_engine"]
            return out
        data = self._safe_json_load(row.settings_json, _DEFAULT_SESSION_SETTINGS)
        if not data.get("tts_engine"):
            data["tts_engine"] = self.get_global_config(db, user)["tts"]["default_engine"]
        return data

    def update_session_settings(
        self, db: Session, user: User, session_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        sid = (session_id or "default").strip() or "default"
        current = self.get_session_settings(db, user, sid)
        for k, v in updates.items():
            if k in _SESSION_SETTING_ALLOWED and v is not None:
                current[k] = v
        text = json.dumps(current, ensure_ascii=False)
        row = (
            db.query(VirtmateSessionSettings)
            .filter(
                VirtmateSessionSettings.user_id == user.id,
                VirtmateSessionSettings.session_id == sid,
            )
            .first()
        )
        if row is None:
            row = VirtmateSessionSettings(user_id=user.id, session_id=sid, settings_json=text)
            db.add(row)
        else:
            row.settings_json = text
        db.commit()
        return current

    def append_message(
        self, db: Session, user: User, session_id: str, role: str, content: str
    ) -> dict[str, Any]:
        sid = (session_id or "default").strip() or "default"
        row = VirtmateSessionMessage(
            user_id=user.id,
            session_id=sid,
            role=role,
            content=content,
        )
        db.add(row)
        db.commit()
        return {
            "role": role,
            "content": content,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    def get_state(self, db: Session, user: User, session_id: str) -> dict[str, Any]:
        sid = (session_id or "default").strip() or "default"
        row = (
            db.query(VirtmateSessionState)
            .filter(
                VirtmateSessionState.user_id == user.id,
                VirtmateSessionState.session_id == sid,
            )
            .first()
        )
        if row is None:
            return {"is_playing": False}
        return self._safe_json_load(row.state_json, {"is_playing": False})

    def update_state(
        self, db: Session, user: User, session_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        sid = (session_id or "default").strip() or "default"
        text = json.dumps(state, ensure_ascii=False)
        row = (
            db.query(VirtmateSessionState)
            .filter(
                VirtmateSessionState.user_id == user.id,
                VirtmateSessionState.session_id == sid,
            )
            .first()
        )
        if row is None:
            row = VirtmateSessionState(user_id=user.id, session_id=sid, state_json=text)
            db.add(row)
        else:
            row.state_json = text
        db.commit()
        return state

    def set_playback_state(
        self,
        db: Session,
        user: User,
        session_id: str,
        is_playing: bool,
        mouth_y: float | None,
    ) -> dict[str, Any]:
        state = self.get_state(db, user, session_id)
        state["is_playing"] = bool(is_playing)
        if mouth_y is not None:
            try:
                y = float(mouth_y)
            except Exception:
                y = 0.0
            state["mouth_y"] = max(0.0, min(1.0, y))
            state["mouth_updated_ts"] = time.time()
        elif not is_playing:
            state["mouth_y"] = 0.0
            state["mouth_updated_ts"] = time.time()
        return self.update_state(db, user, session_id, state)

    def resolve_scene_mouth_y(
        self, db: Session, user: User, session_id: str | None
    ) -> float:
        now = time.time()
        freshness_sec = 1.2

        def pick(payload: dict[str, Any]) -> float:
            if not bool(payload.get("is_playing", False)):
                return 0.0
            ts = payload.get("mouth_updated_ts")
            try:
                tsf = float(ts)
            except Exception:
                return 0.0
            if now - tsf > freshness_sec:
                return 0.0
            y = payload.get("mouth_y")
            try:
                yf = float(y)
            except Exception:
                return 0.0
            return max(0.0, min(1.0, yf))

        sid = (session_id or "").strip()
        if sid:
            y = pick(self.get_state(db, user, sid))
            if y > 0:
                return y
        rows = (
            db.query(VirtmateSessionState)
            .filter(VirtmateSessionState.user_id == user.id)
            .all()
        )
        values: list[float] = []
        for row in rows:
            values.append(pick(self._safe_json_load(row.state_json, {"is_playing": False})))
        return max(values, default=0.0)

    def get_audio_path(self, filename: str) -> Path:
        cleaned = filename.replace("\\", "/").split("/")[-1]
        return self._audio_dir / cleaned

    def _estimate_wav_duration(self, path: Path) -> float:
        try:
            with wave.open(str(path), "rb") as f:
                frames = f.getnframes()
                rate = f.getframerate()
            if rate <= 0:
                return 0.0
            return round(frames / float(rate), 3)
        except Exception:
            return 0.0

    @staticmethod
    def _profile_audio_url(audio_url: str, filename: str) -> str:
        remote = str(audio_url or "").strip()
        if remote:
            return remote
        return f"/me/virtmate/audio/{filename}"

    @staticmethod
    def _extract_audio_bytes_from_json(data: dict[str, Any]) -> tuple[bytes | None, str, str]:
        content_type = str(data.get("content_type") or "audio/wav").strip() or "audio/wav"
        filename = str(data.get("filename") or "").strip()
        for key in ("audio_base64", "audio", "wav_base64", "mp3_base64"):
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            raw = value.strip()
            if raw.startswith("data:") and "," in raw:
                raw = raw.split(",", 1)[1]
            try:
                return base64.b64decode(raw), content_type, filename
            except (binascii.Error, ValueError):
                continue
        return None, content_type, filename

    def _select_gpt_sovits_profile(self, tts_cfg: dict[str, Any]) -> dict[str, Any] | None:
        profiles = tts_cfg.get("gpt_sovits_profiles")
        if not isinstance(profiles, list) or not profiles:
            return None
        active_id = str(tts_cfg.get("gpt_sovits_active_profile_id") or "").strip()
        default_id = str(tts_cfg.get("gpt_sovits_default_profile_id") or "").strip()
        by_id: dict[str, dict[str, Any]] = {}
        for item in profiles:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                by_id[str(item["id"])] = item
        return by_id.get(active_id) or by_id.get(default_id) or next(iter(by_id.values()), None)

    def _get_active_digital_profile(self, db: Session, user: User) -> dict[str, Any] | None:
        digital = self.list_digital_profiles(db, user)
        default_profile = next(
            (
                p
                for p in digital.get("profiles", [])
                if isinstance(p, dict) and str(p.get("id") or "").strip() == "default"
            ),
            deepcopy(_BUILTIN_DEFAULT_DIGITAL_PROFILE),
        )
        active_id = str(digital.get("active_profile_id") or "").strip()
        for item in digital.get("profiles", []):
            if isinstance(item, dict) and str(item.get("id")) == active_id:
                if str(item.get("id") or "").strip() == "default":
                    return deepcopy(default_profile)
                merged = deepcopy(default_profile)
                merged.update(
                    {
                        "id": str(item.get("id") or "").strip() or str(merged.get("id") or "default"),
                        "title": str(item.get("title") or "").strip()
                        or str(merged.get("title") or "默认 Profile"),
                        "created_at": item.get("created_at")
                        if item.get("created_at") is not None
                        else merged.get("created_at"),
                    }
                )
                for key in (
                    "gpt_sovits_prompt",
                    "gpt_sovits_lang",
                    "llm_prompt",
                    "ref_audio_path",
                    "live2d_model_path",
                ):
                    value = str(item.get(key) or "").strip()
                    if value:
                        merged[key] = value
                return merged
        if active_id in {"", "default"}:
            return deepcopy(default_profile)
        return deepcopy(default_profile)

    @staticmethod
    def _candidate_gpt_sovits_base_urls(base_url: str) -> list[str]:
        cleaned = str(base_url or "").strip().rstrip("/")
        out: list[str] = []
        if cleaned:
            out.append(cleaned)
        if "host.docker.internal" in cleaned:
            local = cleaned.replace("host.docker.internal", "127.0.0.1")
            if local not in out:
                out.append(local)
            bridge = cleaned.replace("host.docker.internal", "172.17.0.1")
            if bridge not in out:
                out.append(bridge)
        if cleaned.startswith("http://127.0.0.1"):
            localhost = cleaned.replace("http://127.0.0.1", "http://localhost", 1)
            if localhost not in out:
                out.append(localhost)
        elif cleaned.startswith("http://localhost"):
            loopback = cleaned.replace("http://localhost", "http://127.0.0.1", 1)
            if loopback not in out:
                out.append(loopback)
        return out

    @staticmethod
    def _candidate_gpt_sovits_endpoints(endpoint: str) -> list[str]:
        raw = VirtmateService._normalize_endpoint_path(endpoint)
        # Respect configured endpoint only. Some GPT-SoVITS deployments expose
        # only "/" while others expose only "/tts"; forcing fallback often
        # introduces noisy false errors and delays.
        return [raw]

    def _candidate_gpt_sovits_ref_audio_paths(
        self, user: User | None, ref_audio: str
    ) -> list[str]:
        raw = str(ref_audio or "").strip()
        if not raw:
            return [""]

        out: list[str] = []

        # UI stores uploaded reference audio as API URLs like:
        # /me/virtmate/profile-assets/audio/<filename>
        # GPT-SoVITS expects a filesystem path in its own runtime, so map to the
        # local persisted path when possible.
        prefix = "/me/virtmate/profile-assets/audio/"
        if user is not None and raw.startswith(prefix):
            filename = self._safe_asset_name(raw[len(prefix) :])
            local_path = self._profile_assets_dir / str(user.id) / "audio" / filename
            if local_path.exists():
                prepared = self._prepare_gpt_sovits_ref_audio(local_path)
                shared = self._materialize_gpt_sovits_ref_for_container(user.id, prepared)
                out.append(str(shared))
            return out
        else:
            raw_path = Path(raw)
            if raw_path.exists():
                prepared = self._prepare_gpt_sovits_ref_audio(raw_path)
                owner = str(user.id) if user is not None else "shared"
                shared = self._materialize_gpt_sovits_ref_for_container(owner, prepared)
                out.append(str(shared))
            else:
                out.append(raw)
        return out

    @staticmethod
    def _resolve_gpt_sovits_shared_ref_root() -> Path:
        # GPT-SoVITS container mounts /root/devstack as read-only; host can write.
        # Use a directory under /root/devstack/temp that is confirmed visible
        # inside container.
        candidates = [
            Path("/root/devstack/temp/gpt_sovits_refs"),
            Path("/root/devstack/state/mid-auth/gpt_sovits_refs"),
        ]
        for root in candidates:
            try:
                root.mkdir(parents=True, exist_ok=True)
                return root
            except Exception:
                continue
        fallback = Path("/tmp/gpt_sovits_refs")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _materialize_gpt_sovits_ref_for_container(self, owner: str, src: Path) -> Path:
        if not src.exists():
            return src
        shared_root = self._resolve_gpt_sovits_shared_ref_root() / self._safe_asset_name(owner)
        shared_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.md5(src.read_bytes()).hexdigest()
        target = shared_root / f"{src.stem}-{digest[:12]}{src.suffix.lower() or '.wav'}"
        if not target.exists() or target.stat().st_size != src.stat().st_size:
            shutil.copy2(src, target)
        return target

    def _prepare_gpt_sovits_ref_audio(self, src: Path) -> Path:
        """Prepare reference wav for more stable GPT-SoVITS timbre cloning.

        Some uploaded refs are stereo / high sample-rate / too long, which can
        produce unstable voice color. We normalize wav refs to:
        - mono
        - 16-bit PCM
        - 32k sample-rate
        - max 10s

        Returns the original path when no preparation is needed or failed.
        """
        try:
            if not src.exists() or src.suffix.lower() != ".wav":
                return src
            # Avoid re-processing prepared file repeatedly.
            if src.name.endswith(".vm_ref.wav"):
                return src
            with wave.open(str(src), "rb") as reader:
                channels = int(reader.getnchannels() or 1)
                sample_width = int(reader.getsampwidth() or 2)
                sample_rate = int(reader.getframerate() or 32000)
                nframes = int(reader.getnframes() or 0)
                pcm = reader.readframes(nframes)
            # If already suitable and short enough, keep original.
            duration = (nframes / sample_rate) if sample_rate > 0 else 0.0
            if (
                channels == 1
                and sample_width == 2
                and sample_rate == 32000
                and duration <= 10.0
            ):
                return src
            # Convert bit depth to 16-bit PCM if needed.
            if sample_width != 2:
                pcm = audioop.lin2lin(pcm, sample_width, 2)
                sample_width = 2
            # Down-mix to mono.
            if channels == 2:
                pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
                channels = 1
            elif channels > 2:
                frame_size = sample_width * channels
                pcm = b"".join(pcm[i : i + sample_width] for i in range(0, len(pcm), frame_size))
                channels = 1
            # Re-sample to 32k.
            if sample_rate != 32000:
                pcm, _ = audioop.ratecv(
                    pcm, sample_width, channels, sample_rate, 32000, None
                )
                sample_rate = 32000
            # Trim to max 10 seconds.
            max_frames = int(10.0 * sample_rate)
            max_bytes = max_frames * sample_width * channels
            if len(pcm) > max_bytes:
                pcm = pcm[:max_bytes]
            prepared = src.with_name(f"{src.stem}.vm_ref.wav")
            with wave.open(str(prepared), "wb") as writer:
                writer.setnchannels(channels)
                writer.setsampwidth(sample_width)
                writer.setframerate(sample_rate)
                writer.writeframes(pcm)
            return prepared
        except Exception:
            return src

    @staticmethod
    def _stream_gpt_sovits_request(
        url: str, payload: dict[str, Any], timeout_sec: int
    ) -> tuple[bytes, str]:
        """POST to a GPT-SoVITS endpoint, tolerating its broken chunked encoding.

        GPT-SoVITS uses chunked transfer-encoding but closes the TCP connection
        without a proper ``0\\r\\n\\r\\n`` terminator.  Both ``httpx.post()`` and
        ``httpx.stream()`` rely on h11 which is strict about this and may raise
        ``RemoteProtocolError`` *before* yielding any data.

        ``urllib.request`` (backed by ``http.client``) is far more lenient:
        ``response.read()`` returns all bytes received before the connection
        closed, which is exactly the complete audio payload.

        Returns ``(body_bytes, content_type)`` on success.
        Raises on hard failures (connection refused, 4xx/5xx, zero bytes).
        """
        import http.client as _http_client
        import logging as _logging
        import urllib.error
        import urllib.request

        _log = _logging.getLogger(__name__)

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json", "Accept": "*/*"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                content_type = str(resp.headers.get("Content-Type") or "").lower()
                try:
                    body = resp.read()
                except _http_client.IncompleteRead as partial:
                    body = partial.partial
                    _log.info(
                        "GPT-SoVITS IncompleteRead from %s – recovered %d bytes",
                        url,
                        len(body),
                    )
        except urllib.error.HTTPError as exc:
            raise httpx.HTTPStatusError(
                f"Client error '{exc.code}' for url '{url}'",
                request=httpx.Request("POST", url),
                response=httpx.Response(exc.code),
            ) from exc
        except urllib.error.URLError as exc:
            raise OSError(str(exc.reason)) from exc

        if not body:
            raise RuntimeError(f"GPT-SoVITS returned 0 bytes from {url}")

        _log.info("GPT-SoVITS OK from %s – %d bytes, content-type=%s", url, len(body), content_type)
        return body, content_type

    def _synthesize_gpt_sovits_api(
        self,
        text: str,
        global_cfg: dict[str, Any],
        active_profile: dict[str, Any] | None = None,
        user: User | None = None,
    ) -> dict[str, Any]:
        tts = global_cfg["tts"]
        profile = self._select_gpt_sovits_profile(tts)
        if not profile:
            return {
                "audio_url": "",
                "engine": "GPT-SoVITS API",
                "duration": 0.0,
                "filename": "",
                "error": "未配置 GPT-SoVITS profile",
            }
        base_url = str(profile.get("base_url") or "").rstrip("/")
        endpoint = self._normalize_endpoint_path(profile.get("endpoint"))
        timeout_sec = int(str(tts.get("local_timeout_sec", "180")))
        text_lang = str((active_profile or {}).get("gpt_sovits_lang") or profile.get("text_lang") or "").strip() or "auto"
        prompt_text = str((active_profile or {}).get("gpt_sovits_prompt") or profile.get("prompt_text") or "").strip()
        ref_audio = str(
            (active_profile or {}).get("ref_audio_path") or profile.get("ref_audio") or ""
        ).strip()
        ref_audio_candidates = self._candidate_gpt_sovits_ref_audio_paths(user, ref_audio)
        if ref_audio and not ref_audio_candidates:
            return {
                "audio_url": "",
                "engine": "GPT-SoVITS API",
                "duration": 0.0,
                "filename": "",
                "error": f"参考音频文件不存在或不可访问：{ref_audio}",
                "ref_audio_requested": ref_audio,
                "ref_audio_used": None,
            }
        common_payload: dict[str, Any] = {"text": text}
        extra = profile.get("extra_json")
        if isinstance(extra, dict):
            common_payload.update(extra)
        collected_bytes: bytes | None = None
        collected_content_type: str = ""
        used_base_url = ""
        used_endpoint = ""
        used_ref_audio = ""
        errors: list[str] = []
        for candidate_base in self._candidate_gpt_sovits_base_urls(base_url):
            for candidate_endpoint in self._candidate_gpt_sovits_endpoints(endpoint):
                url = f"{candidate_base}{candidate_endpoint}"
                for candidate_ref_audio in ref_audio_candidates:
                    payload = dict(common_payload)
                    if candidate_endpoint == "/tts":
                        payload["text_lang"] = text_lang
                        payload["prompt_lang"] = text_lang
                        if prompt_text:
                            payload["prompt_text"] = prompt_text
                        if candidate_ref_audio:
                            payload["ref_audio_path"] = candidate_ref_audio
                        for source, target in (
                            ("top_k", "top_k"),
                            ("top_p", "top_p"),
                            ("temperature", "temperature"),
                        ):
                            if profile.get(source) is not None:
                                payload[target] = profile.get(source)
                        if profile.get("speed") is not None:
                            payload["speed_factor"] = profile.get("speed")
                    else:
                        # Treat "/" and any custom non-/tts endpoint as api.py style.
                        payload.pop("top_k", None)
                        payload.pop("top_p", None)
                        payload.pop("temperature", None)
                        payload["text_language"] = text_lang
                        payload["prompt_language"] = text_lang
                        if candidate_ref_audio:
                            payload["refer_wav_path"] = candidate_ref_audio
                            # api.py fallback logic switches to default reference
                            # whenever prompt_text is empty. Force a non-empty
                            # prompt_text to ensure custom refer_wav_path is used.
                            payload["prompt_text"] = prompt_text or "嗯。"
                        elif prompt_text:
                            payload["prompt_text"] = prompt_text
                        if profile.get("speed") is not None:
                            payload["speed"] = profile.get("speed")
                    try:
                        collected_bytes, collected_content_type = self._stream_gpt_sovits_request(
                            url, payload, timeout_sec
                        )
                    except Exception as exc:
                        ref_hint = candidate_ref_audio or "<empty>"
                        errors.append(f"{url} [ref={ref_hint}]: {exc}")
                        continue
                    used_base_url = candidate_base
                    used_endpoint = candidate_endpoint
                    used_ref_audio = candidate_ref_audio
                    break
                if collected_bytes is not None:
                    break
            if collected_bytes is not None:
                break
        if collected_bytes is None:
            detail = "; ".join(errors) if errors else "unknown error"
            return {
                "audio_url": "",
                "engine": "GPT-SoVITS API",
                "duration": 0.0,
                "filename": "",
                "error": f"GPT-SoVITS 调用失败：{detail}",
                "ref_audio_requested": ref_audio or None,
                "ref_audio_used": None,
            }
        content_type = collected_content_type
        if "application/json" in content_type:
            try:
                data = json.loads(collected_bytes)
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            audio_url = str(data.get("audio_url") or data.get("url") or "").strip()
            audio_bytes, json_content_type, json_filename = self._extract_audio_bytes_from_json(data)
            if audio_bytes is None:
                if audio_url:
                    return {
                        "audio_url": audio_url,
                        "engine": "GPT-SoVITS API",
                        "duration": 0.0,
                        "filename": "",
                        "ref_audio_requested": ref_audio or None,
                        "ref_audio_used": used_ref_audio or None,
                        "base_url_used": used_base_url or None,
                        "endpoint_used": used_endpoint or None,
                    }
                return {
                    "audio_url": "",
                    "engine": "GPT-SoVITS API",
                    "duration": 0.0,
                    "filename": "",
                    "error": f"GPT-SoVITS 未返回可用音频: {data}",
                    "ref_audio_requested": ref_audio or None,
                    "ref_audio_used": used_ref_audio or None,
                    "base_url_used": used_base_url or None,
                    "endpoint_used": used_endpoint or None,
                }
            ext = ".wav"
            if "mpeg" in json_content_type:
                ext = ".mp3"
            filename = json_filename or f"{uuid.uuid4().hex}{ext}"
            path = self._audio_dir / filename
            path.write_bytes(audio_bytes)
            return {
                "audio_url": self._profile_audio_url("", filename),
                "engine": "GPT-SoVITS API",
                "duration": self._estimate_wav_duration(path) if ext == ".wav" else 0.0,
                "filename": filename,
                "ref_audio_requested": ref_audio or None,
                "ref_audio_used": used_ref_audio or None,
                "base_url_used": used_base_url or None,
                "endpoint_used": used_endpoint or None,
            }
        ext = ".wav"
        if "mpeg" in content_type:
            ext = ".mp3"
        elif "ogg" in content_type:
            ext = ".ogg"
        filename = f"{uuid.uuid4().hex}{ext}"
        path = self._audio_dir / filename
        path.write_bytes(collected_bytes)
        return {
            "audio_url": self._profile_audio_url("", filename),
            "engine": "GPT-SoVITS API",
            "duration": self._estimate_wav_duration(path) if ext == ".wav" else 0.0,
            "filename": filename,
            "ref_audio_requested": ref_audio or None,
            "ref_audio_used": used_ref_audio or None,
            "base_url_used": used_base_url or None,
            "endpoint_used": used_endpoint or None,
        }

    async def synthesize_text(
        self,
        db: Session,
        user: User,
        text: str,
        tts_engine: str | None,
    ) -> dict[str, Any]:
        global_cfg = self.get_global_config(db, user)
        engine = (tts_engine or global_cfg["tts"].get("default_engine") or "云端edge-tts").strip()
        if engine == "关闭语音合成":
            return {"audio_url": "", "engine": engine, "duration": 0.0, "filename": ""}
        if engine == "云端Paddle-TTS":
            return await asyncio.to_thread(self._synthesize_paddle_tts, text)
        if engine == "GPT-SoVITS API":
            active_profile = self._get_active_digital_profile(db, user)
            return await asyncio.to_thread(
                self._synthesize_gpt_sovits_api, text, global_cfg, active_profile, user
            )
        if engine in {"本地GPT-SoVITS", "本地CosyVoice", "本地Index-TTS", "本地VoxCPM"}:
            return await asyncio.to_thread(self._synthesize_local_tts, engine, text, global_cfg)
        return {"audio_url": "", "engine": engine, "duration": 0.0, "filename": ""}

    def _synthesize_paddle_tts(self, text: str) -> dict[str, Any]:
        try:
            url = f"https://fanyi.baidu.com/gettts?lan=zh&spd=5&text={text}"
            res = httpx.get(url, timeout=60)
            res.raise_for_status()
        except Exception as exc:
            return {
                "audio_url": "",
                "engine": "云端Paddle-TTS",
                "duration": 0.0,
                "filename": "",
                "error": f"paddle tts failed: {exc}",
            }
        filename = f"{uuid.uuid4().hex}.mp3"
        path = self._audio_dir / filename
        path.write_bytes(res.content)
        return {
            "audio_url": f"/me/virtmate/audio/{filename}",
            "engine": "云端Paddle-TTS",
            "duration": 0.0,
            "filename": filename,
        }

    def _synthesize_local_tts(
        self,
        engine: str,
        text: str,
        global_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        tts = global_cfg["tts"]
        local_ip = str(tts.get("local_host", "127.0.0.1"))
        timeout_sec = int(str(tts.get("local_timeout_sec", "180")))
        gpt_port = str(tts.get("gpt_sovits_port", "9880"))
        cosy_port = str(tts.get("cosyvoice_port", "9881"))
        index_port = str(tts.get("indextts_port", "9884"))
        voxcpm_port = str(tts.get("voxcpm_port", "9885"))
        if engine == "本地GPT-SoVITS":
            url = f"http://{local_ip}:{gpt_port}/tts?text={text}&text_lang=zh"
        elif engine == "本地CosyVoice":
            url = f"http://{local_ip}:{cosy_port}/cosyvoice/?text={text}"
        elif engine == "本地Index-TTS":
            url = f"http://{local_ip}:{index_port}/indextts/?text={text}"
        else:
            url = f"http://{local_ip}:{voxcpm_port}/voxcpm/?text={text}"
        try:
            res = httpx.get(url, timeout=timeout_sec)
            res.raise_for_status()
        except Exception as exc:
            return {
                "audio_url": "",
                "engine": engine,
                "duration": 0.0,
                "filename": "",
                "error": f"{engine}调用失败：{exc}",
            }
        filename = f"{uuid.uuid4().hex}.wav"
        path = self._audio_dir / filename
        path.write_bytes(res.content)
        return {
            "audio_url": f"/me/virtmate/audio/{filename}",
            "engine": engine,
            "duration": self._estimate_wav_duration(path),
            "filename": filename,
        }

    async def asr_recognize(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        def call_asr() -> dict[str, Any]:
            try:
                res = httpx.post(
                    f"{self._asr_base_url()}/api/asr/recognize",
                    files={"audio": (filename or "voice.wav", audio_bytes, content_type)},
                    timeout=self._asr_timeout(),
                )
                payload = res.json() if res.content else {}
                status_code = int(getattr(res, "status_code", 0) or 0)
                ok = 200 <= status_code < 300
                if not isinstance(payload, dict):
                    return {"ok": False, "error": f"invalid asr response: {payload}"}
                if not ok:
                    return {"ok": False, "error": f"ASR API HTTP {status_code}: {payload}"}
                return payload
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        return await asyncio.to_thread(call_asr)

    async def fetch_asr_status(self) -> dict[str, Any]:
        def call_status() -> dict[str, Any]:
            try:
                res = httpx.get(
                    f"{self._asr_base_url()}/api/asr/status",
                    timeout=self._asr_timeout(),
                )
                payload = res.json() if res.content else {}
                status_code = int(getattr(res, "status_code", 0) or 0)
                ok = 200 <= status_code < 300
                if ok and isinstance(payload, dict) and isinstance(payload.get("asr"), dict):
                    return payload["asr"]
                return {"last_error": f"ASR API HTTP {status_code}: {payload}"}
            except Exception as exc:
                return {"last_error": f"ASR API unavailable: {exc}"}

        return await asyncio.to_thread(call_status)

    async def runtime_hardware(self, db: Session, user: User) -> dict[str, Any]:
        gpu: dict[str, Any] = {"cuda_available": False, "name": "", "vram_total_mb": 0}
        if torch is not None:
            try:
                if torch.cuda.is_available():
                    gpu["cuda_available"] = True
                    gpu["name"] = torch.cuda.get_device_name(0)
            except Exception:
                pass
        if nv is not None:
            try:
                nv.nvmlInit()
                handle = nv.nvmlDeviceGetHandleByIndex(0)
                mem = nv.nvmlDeviceGetMemoryInfo(handle)
                name = nv.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="ignore")
                gpu["name"] = gpu["name"] or str(name)
                gpu["vram_total_mb"] = int(mem.total // (1024 * 1024))
                gpu["cuda_available"] = True
            except Exception:
                pass
        if not gpu["cuda_available"]:
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=3,
                ).strip()
                if out:
                    first = out.splitlines()[0]
                    parts = [x.strip() for x in first.split(",")]
                    gpu["name"] = parts[0] if parts else ""
                    if len(parts) > 1 and parts[1].isdigit():
                        gpu["vram_total_mb"] = int(parts[1])
                    gpu["cuda_available"] = True
            except Exception:
                pass
        return {
            "gpu": gpu,
            "asr": await self.fetch_asr_status(),
            "tts": {
                "audio_cache_dir": str(self._audio_dir),
            },
            "global": self.get_global_config(db, user),
        }

    @staticmethod
    def _get_message_list(messages_map: dict[str, Any], message_id: str | None) -> list[dict[str, Any]]:
        if not messages_map or not message_id:
            return []
        current = messages_map.get(message_id)
        if not current:
            return []
        out: list[dict[str, Any]] = []
        visited: set[str] = set()
        while current:
            mid = current.get("id")
            if mid is not None:
                s = str(mid)
                if s in visited:
                    break
                visited.add(s)
            out.append(current)
            parent_id = current.get("parentId")
            current = messages_map.get(parent_id) if parent_id else None
        out.reverse()
        return out

    @staticmethod
    def _message_body_text(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text") is not None:
                    parts.append(str(item["text"]))
            return "\n".join(parts).strip()
        if content is None:
            return ""
        return str(content).strip()

    def _openai_thread_from_chain(self, chain: list[dict[str, Any]]) -> list[dict[str, str]]:
        thread: list[dict[str, str]] = []
        for message in chain:
            role = message.get("role")
            if role not in ("user", "assistant"):
                continue
            thread.append({"role": str(role), "content": self._message_body_text(message)})
        return thread

    @staticmethod
    def _extract_delta_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        delta = first.get("delta")
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content")
        if content is None:
            return ""
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text") is not None:
                    parts.append(str(item["text"]))
            return "".join(parts)
        return str(content)

    @staticmethod
    def _parse_assistant_plain(data: dict[str, Any]) -> str:
        if data.get("task_id") and not data.get("choices"):
            raise VirtmateServiceError(503, "openwebui returned async task")
        err = data.get("error")
        if err:
            raise VirtmateServiceError(503, "openwebui completion error")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise VirtmateServiceError(503, "openwebui completion missing choices")
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(msg, dict):
            raise VirtmateServiceError(503, "openwebui completion invalid message")
        content = msg.get("content")
        if content is None and msg.get("reasoning_content") is not None:
            content = msg.get("reasoning_content")
        if content is None:
            return ""
        if isinstance(content, list):
            return VirtmateService._message_body_text(msg)
        return str(content)

    @staticmethod
    def _append_user_assistant_pair(
        inner: dict[str, Any],
        *,
        leaf_parent_id: str | None,
        user_text: str,
        assistant_text: str,
        model_id: str,
    ) -> tuple[str, str]:
        history = inner.setdefault("history", {})
        messages: dict[str, Any] = history.setdefault("messages", {})
        user_msg_id = uuid.uuid4().hex
        assistant_msg_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        user_node: dict[str, Any] = {
            "id": user_msg_id,
            "parentId": leaf_parent_id,
            "childrenIds": [assistant_msg_id],
            "role": "user",
            "content": user_text,
            "timestamp": now,
        }
        assistant_node: dict[str, Any] = {
            "id": assistant_msg_id,
            "parentId": user_msg_id,
            "childrenIds": [],
            "role": "assistant",
            "content": assistant_text,
            "model": model_id,
            "timestamp": now + 1,
        }
        messages[user_msg_id] = user_node
        messages[assistant_msg_id] = assistant_node
        if leaf_parent_id and leaf_parent_id in messages:
            parent = messages[leaf_parent_id]
            children = parent.setdefault("childrenIds", [])
            if user_msg_id not in children:
                children.append(user_msg_id)
        history["currentId"] = assistant_msg_id
        return user_msg_id, assistant_msg_id

    @staticmethod
    def _maybe_set_title_from_first_message(inner: dict[str, Any], user_text: str) -> None:
        title = str(inner.get("title") or "").strip()
        if title in {"", "New Chat"}:
            line = user_text.strip().split("\n", 1)[0].strip()
            inner["title"] = line[:120] if line else "New Chat"

    def _openwebui_chat_turn(
        self,
        acting_uid: str,
        client: OpenWebUIClient,
        *,
        model_id: str,
        user_text: str,
        conversation_id: str | None,
        system_prompt: str | None,
        stream: bool,
        on_delta: Callable[[str, str], None] | None,
    ) -> tuple[str, str]:
        text = user_text.strip()
        if not text:
            raise VirtmateServiceError(400, "message text must not be empty")
        mid = (model_id or "").strip()
        if not mid:
            raise VirtmateServiceError(400, "model is required")

        if conversation_id and conversation_id.strip():
            chat_id = conversation_id.strip()
            try:
                data = client.get_chat(acting_uid, chat_id)
            except OpenWebUIClientError as exc:
                raise self._map_openwebui_error(exc) from exc
            inner = deepcopy(data.get("chat") if isinstance(data.get("chat"), dict) else {})
            if not inner:
                raise VirtmateServiceError(503, "openwebui chat payload invalid")
        else:
            inner = {
                "title": "New Chat",
                "models": [mid],
                "history": {"messages": {}, "currentId": None},
                "tags": [],
            }
            try:
                created = client.create_chat(acting_uid, chat=inner)
            except OpenWebUIClientError as exc:
                raise self._map_openwebui_error(exc) from exc
            chat_id = str(
                created.get("id")
                or (created.get("chat") if isinstance(created.get("chat"), dict) else {}).get("id")
                or ""
            )
            if not chat_id:
                raise VirtmateServiceError(503, "openwebui create chat missing id")

        history = inner.setdefault("history", {})
        messages_map: dict[str, Any] = history.setdefault("messages", {})
        leaf_parent_id = history.get("currentId")
        leaf_str = str(leaf_parent_id) if leaf_parent_id else None
        chain = self._get_message_list(messages_map, leaf_str)
        openai_prev = self._openai_thread_from_chain(chain)
        openai_messages: list[dict[str, str]] = []
        prompt = (system_prompt or "").strip()
        if prompt:
            openai_messages.append({"role": "system", "content": prompt})
        openai_messages.extend(openai_prev)
        openai_messages.append({"role": "user", "content": text})
        completion_payload = {"model": mid, "messages": openai_messages, "stream": bool(stream)}

        if stream:
            try:
                stream_holder = client.proxy_to_openwebui_stream(
                    acting_uid,
                    method="POST",
                    downstream_path="/api/v1/chat/completions",
                    content=json.dumps(completion_payload, ensure_ascii=False).encode("utf-8"),
                    extra_headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                )
            except OpenWebUIClientError as exc:
                raise self._map_openwebui_error(exc) from exc
            full = ""
            buf = ""
            for chunk in stream_holder.iter_bytes():
                if not chunk:
                    continue
                try:
                    buf += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body or body == "[DONE]":
                        continue
                    try:
                        data = json.loads(body)
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    err = data.get("error")
                    if err:
                        raise VirtmateServiceError(503, "openwebui completion error")
                    delta = self._extract_delta_content(data)
                    if not delta:
                        continue
                    full = f"{full}{delta}"
                    if on_delta is not None:
                        on_delta(delta, full)
            assistant_plain = full
        else:
            try:
                completion = client.chat_completion(acting_uid, completion_payload)
            except OpenWebUIClientError as exc:
                raise self._map_openwebui_error(exc) from exc
            assistant_plain = self._parse_assistant_plain(completion)

        self._maybe_set_title_from_first_message(inner, text)
        if mid and not inner.get("models"):
            inner["models"] = [mid]
        self._append_user_assistant_pair(
            inner,
            leaf_parent_id=leaf_str,
            user_text=text,
            assistant_text=assistant_plain,
            model_id=mid,
        )
        try:
            client.update_chat(acting_uid, chat_id, chat=inner)
        except OpenWebUIClientError as exc:
            raise self._map_openwebui_error(exc) from exc
        return assistant_plain, chat_id

    async def chat_send(
        self,
        db: Session,
        user: User,
        client: OpenWebUIClient,
        *,
        session_id: str,
        text: str,
        model: str,
        conversation_id: str | None,
        with_tts: bool,
        stream: bool,
        on_delta: Callable[[str, str], None] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        settings = self.get_session_settings(db, user, session_id)
        profile_prompt = str((self._get_active_digital_profile(db, user) or {}).get("llm_prompt") or "").strip()
        system_prompt = profile_prompt or str(settings.get("prompt") or "").strip() or None
        user_record = self.append_message(db, user, session_id, "user", text)
        try:
            acting_uid = resolve_openwebui_acting_uid(db, user)
        except AiChatServiceError as exc:
            raise VirtmateServiceError(exc.status_code, exc.detail) from None
        try:
            assistant_text, chat_id = await asyncio.to_thread(
                self._openwebui_chat_turn,
                acting_uid,
                client,
                model_id=model,
                user_text=text,
                conversation_id=conversation_id,
                system_prompt=system_prompt,
                stream=stream,
                on_delta=on_delta,
            )
        except VirtmateServiceError:
            raise
        except Exception as exc:
            raise VirtmateServiceError(502, str(exc)) from exc
        assistant_record = self.append_message(
            db, user, session_id, "assistant", assistant_text
        )
        if with_tts and settings.get("tts_engine") != "关闭语音合成":
            tts_res = await self.synthesize_text(
                db, user, assistant_text, settings.get("tts_engine")
            )
        else:
            tts_res = {"audio_url": "", "engine": "关闭语音合成", "duration": 0.0, "filename": ""}
        assistant_record["tts"] = tts_res
        return user_record, assistant_record, chat_id


virtmate_service = VirtmateService()

