from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RuntimeConfig:
    root_dir: Path
    data_dir: Path
    dist_dir: Path
    config_path: Path
    more_set_path: Path
    cloud_keys_path: Path
    preference_path: Path
    config: dict[str, Any]
    more_set: dict[str, Any]
    cloud_keys: dict[str, Any]
    preference: dict[str, Any]
    _lock: threading.Lock

    @classmethod
    def load(cls, root_dir: Path) -> "RuntimeConfig":
        data_dir = root_dir / "data"
        dist_dir = root_dir / "dist"
        config_path = data_dir / "db" / "config.json"
        more_set_path = data_dir / "set" / "more_set.json"
        cloud_keys_path = data_dir / "set" / "cloud_ai_key_set.json"
        preference_path = data_dir / "db" / "preference.json"
        config = cls._load_json(config_path, {})
        more_set = cls._load_json(more_set_path, {})
        cloud_keys = cls._load_json(cloud_keys_path, {})
        preference = cls._load_json(preference_path, {})
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            dist_dir=dist_dir,
            config_path=config_path,
            more_set_path=more_set_path,
            cloud_keys_path=cloud_keys_path,
            preference_path=preference_path,
            config=config,
            more_set=more_set,
            cloud_keys=cloud_keys,
            preference=preference,
            _lock=threading.Lock(),
        )

    @staticmethod
    def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _dump_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)

    def refresh(self) -> None:
        with self._lock:
            self.config = self._load_json(self.config_path, self.config)
            self.more_set = self._load_json(self.more_set_path, self.more_set)
            self.cloud_keys = self._load_json(self.cloud_keys_path, self.cloud_keys)
            self.preference = self._load_json(self.preference_path, self.preference)

    def update_global(
        self,
        config_updates: dict[str, Any] | None = None,
        more_set_updates: dict[str, Any] | None = None,
        preference_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if config_updates:
                for key, value in config_updates.items():
                    if value is not None:
                        self.config[key] = value
                self._dump_json(self.config_path, self.config)
            if more_set_updates:
                for key, value in more_set_updates.items():
                    if value is not None:
                        self.more_set[key] = value
                self._dump_json(self.more_set_path, self.more_set)
            if preference_updates:
                for key, value in preference_updates.items():
                    if value is not None:
                        self.preference[key] = value
                self._dump_json(self.preference_path, self.preference)
            return self.get_global_view(mask_secrets=False)

    def get_global_view(self, mask_secrets: bool = True) -> dict[str, Any]:
        _ = mask_secrets  # 保留参数以兼容旧调用；已无密钥字段需打码
        return {
            "openwebui": {
                "base_url": (os.environ.get("OPENWEBUI_BASE_URL") or "http://127.0.0.1:8080").strip().rstrip("/"),
                "user_id_header": (os.environ.get("OPENWEBUI_USER_ID_HEADER") or "user-id").strip()
                or "user-id",
            },
            "asr": {
                "engine": self.config.get("ASR引擎", "faster_whisper_cuda"),
                "model": self.config.get("ASR模型", "large-v3"),
                "device": self.config.get("ASR设备", "cuda"),
                "compute_type": self.config.get("ASR计算精度", "float16"),
                "cuda_device_index": str(self.config.get("ASR_GPU序号", "0")),
                "disable_auto_fallback": str(self.config.get("ASR禁用自动回退", "关闭")) == "开启",
                "sensitivity": self.config.get("语音识别灵敏度", "中"),
                "voiceprint_switch": self.config.get("声纹识别", "关闭"),
                "voiceprint_threshold": self.more_set.get("声纹识别阈值", "0.6"),
            },
            "tts": {
                "local_host": self.more_set.get("本地TTS服务器IP", "127.0.0.1"),
                "gpt_sovits_port": self.more_set.get("GPT-SoVITS端口", "9880"),
                "cosyvoice_port": self.more_set.get("CosyVoice端口", "9881"),
                "indextts_port": self.more_set.get("Index-TTS端口", "9884"),
                "voxcpm_port": self.more_set.get("VoxCPM端口", "9885"),
                "local_timeout_sec": self.more_set.get("本地TTS超时时间秒", "180"),
                "fallback_engine": self.more_set.get("本地TTS失败回退引擎", "云端edge-tts"),
                "default_engine": self.preference.get("语音合成引擎", "云端edge-tts"),
            },
        }

    def get_default_session_profile(self) -> dict[str, Any]:
        return {
            "username": self.config.get("用户名", "开拓者"),
            "mate_name": self.config.get("虚拟伙伴名称", "小月"),
            "prompt": self.config.get("虚拟伙伴人设", ""),
            "tts_engine": self.preference.get("语音合成引擎", "云端edge-tts"),
            "cam_permission": self.config.get("摄像头权限", "关闭"),
        }

    def get_server_ports(self) -> dict[str, int]:
        return {
            "chatweb_port": int(self.config.get("对话网页端口", 5260)),
            "live2d_port": int(self.config.get("L2D角色网页端口", 5261)),
            "mmd_port": int(self.config.get("MMD角色网页端口", 5262)),
            "vrm_port": int(self.config.get("VRM角色网页端口", 5263)),
        }

