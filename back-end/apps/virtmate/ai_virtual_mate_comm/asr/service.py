from __future__ import annotations

import os

# faster-whisper/ctranslate2 在首次 import 前生效：缓解 cuda_malloc_async 误报 OOM、PyTorch 与多卡默认设备不一致带来的碎片问题
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("CT2_CUDA_ALLOCATOR", "cub_caching")

import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

try:
    import av
except Exception:  # pragma: no cover
    av = None

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover
    WhisperModel = None

try:
    import sherpa_onnx
except Exception:  # pragma: no cover
    sherpa_onnx = None

from server.config import RuntimeConfig

# 浏览器上传整段录音时，不再使用桌面端「静音停录」用的 silence_duration（中=2s→+0.5 即 2.5s），
# 否则短句（1～2 秒）会恒返回空字符串，前端显示「无有效文本」。
MIN_UPLOAD_AUDIO_SEC = 0.35


class AsrService:
    def __init__(self, runtime: RuntimeConfig) -> None:
        self.runtime = runtime
        self.asr_model_path = runtime.data_dir / "model" / "ASR" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
        self.vp_model_path = runtime.data_dir / "model" / "SpeakerID" / "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
        self.cache_voiceprint_path = runtime.data_dir / "cache" / "voiceprint" / "myvoice.wav"
        self.silence_duration_map = {"高": 1, "中": 2, "低": 3}
        self.asr_engine = "faster_whisper_cuda"
        self.asr_model_name = "large-v3"
        self.asr_device = "cuda"
        self.asr_compute_type = "float16"
        self.asr_gpu_index_cfg = 0
        self.voiceprint_threshold = 0.6
        self.asr_sensitivity = "中"
        self.voiceprint_switch = "关闭"
        self.silence_duration = 3
        self._recognizer = None
        self._fw_model = None
        self._vp_extractor = None
        self._vp_embedding_ref = None
        self._recognizer_error: str | None = None
        self._fw_error: str | None = None
        self._fw_actual_device = self.asr_device
        self._fw_actual_compute_type = self.asr_compute_type
        self._fw_auto_fallback = False
        self.asr_auto_fallback_allowed = True
        self._sync_runtime_fields(force_reset=True)

    def _sync_runtime_fields(self, force_reset: bool = False) -> None:
        new_engine = str(self.runtime.config.get("ASR引擎", "faster_whisper_cuda"))
        new_model = str(self.runtime.config.get("ASR模型", "large-v3"))
        new_device = str(self.runtime.config.get("ASR设备", "cuda"))
        new_compute_type = str(self.runtime.config.get("ASR计算精度", "float16"))
        new_sensitivity = str(self.runtime.config.get("语音识别灵敏度", "中"))
        new_voiceprint_switch = str(self.runtime.config.get("声纹识别", "关闭"))
        new_voiceprint_threshold = float(self.runtime.more_set.get("声纹识别阈值", 0.6))
        raw_gpu_idx = str(self.runtime.config.get("ASR_GPU序号", "0")).strip()
        try:
            new_gpu_idx_cfg = max(0, int(raw_gpu_idx))
        except ValueError:
            new_gpu_idx_cfg = 0
        # 「开启」= 禁用跨设备(CUDA→CPU)、引擎互切、VAD 二次等；同卡上仍可按精度链降级(float16→int8_float16→int8)
        new_auto_fb_allowed = str(self.runtime.config.get("ASR禁用自动回退", "关闭")) != "开启"
        changed = force_reset or any(
            [
                new_engine != self.asr_engine,
                new_model != self.asr_model_name,
                new_device != self.asr_device,
                new_compute_type != self.asr_compute_type,
                new_gpu_idx_cfg != self.asr_gpu_index_cfg,
                new_auto_fb_allowed != self.asr_auto_fallback_allowed,
                new_sensitivity != self.asr_sensitivity,
                new_voiceprint_switch != self.voiceprint_switch,
                new_voiceprint_threshold != self.voiceprint_threshold,
            ]
        )
        self.asr_auto_fallback_allowed = new_auto_fb_allowed
        self.asr_engine = new_engine
        self.asr_model_name = new_model
        self.asr_device = new_device
        self.asr_compute_type = new_compute_type
        self.asr_gpu_index_cfg = new_gpu_idx_cfg
        self.asr_sensitivity = new_sensitivity
        self.voiceprint_switch = new_voiceprint_switch
        self.voiceprint_threshold = new_voiceprint_threshold
        self.silence_duration = self.silence_duration_map.get(self.asr_sensitivity, 3)
        if changed:
            self._recognizer = None
            self._fw_model = None
            self._recognizer_error = None
            self._fw_error = None
            self._fw_actual_device = self.asr_device
            self._fw_actual_compute_type = self.asr_compute_type
            self._fw_auto_fallback = False

    def _cuda_device_index(self) -> int:
        """faster-whisper/ctranslate2 使用的物理 GPU 序号。环境变量优先，便于与其它 CUDA 服务分区。"""
        env = os.environ.get("VIRTMATE_ASR_CUDA_DEVICE", "").strip()
        if env.isdigit():
            return max(0, int(env))
        return self.asr_gpu_index_cfg

    def _fw_model_kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "download_root": str(self.runtime.data_dir / "model" / "ASR"),
            "local_files_only": True,
        }
        if self.asr_device == "cuda":
            kw["device_index"] = self._cuda_device_index()
        return kw

    @staticmethod
    def _looks_like_cuda_runtime_error(msg: str) -> bool:
        lowered = msg.lower()
        return any(
            token in lowered
            for token in [
                "libcublas",
                "libcudnn",
                "libcuda",
                "cuda driver",
                "cuda runtime",
                "failed to load library",
                "cannot be loaded",
                "cudart",
                "busy or unavailable",
                "device is busy",
            ]
        )

    @staticmethod
    def _looks_like_cuda_oom(msg: str) -> bool:
        """ctranslate2/faster-whisper 在显存碎片或瞬时峰值时常报 OOM，但 nvidia-smi 仍显示有余量。"""
        m = msg.lower()
        return any(
            token in m
            for token in (
                "out of memory",
                "outofmemory",
                "cuda error: out of memory",
                "cublas_status_alloc_failed",
                "allocation failed",
                "failed to allocate",
            )
        )

    def _release_torch_cuda_memory_for_asr_gpu(self) -> None:
        """减轻与其它 PyTorch 进程同卡共存时的碎片/占用，便于 ctranslate2 连续块申请。"""
        if self.asr_device != "cuda":
            return
        try:
            import torch

            if not torch.cuda.is_available():
                return
            idx = self._cuda_device_index()
            if idx < 0 or idx >= torch.cuda.device_count():
                return
            with torch.cuda.device(idx):
                torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
        except Exception:
            pass

    def _ensure_recognizer(self) -> None:
        if self._recognizer is not None or sherpa_onnx is None:
            return
        model = str(self.asr_model_path / "model.int8.onnx")
        tokens = str(self.asr_model_path / "tokens.txt")
        try:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model,
                tokens=tokens,
                use_itn=True,
                num_threads=max(1, int(os.cpu_count() or 2) - 1),
            )
        except Exception as e:
            self._recognizer_error = str(e)
            self._recognizer = None

    def _ensure_fw_model(self) -> None:
        if self._fw_model is not None or WhisperModel is None:
            return

        download_root = str(self.runtime.data_dir / "model" / "ASR")

        def load_whisper(device: str, compute_type: str) -> tuple[Any, str | None]:
            try:
                kw: dict[str, Any] = {
                    "download_root": download_root,
                    "local_files_only": True,
                }
                if device == "cuda":
                    kw.update(self._fw_model_kwargs())
                    try:
                        import torch

                        if torch.cuda.is_available():
                            di = kw.get("device_index", 0)
                            idx = int(di[0] if isinstance(di, list) else di)
                            if 0 <= idx < torch.cuda.device_count():
                                torch.cuda.set_device(idx)
                    except Exception:
                        pass
                model = WhisperModel(
                    self.asr_model_name,
                    device=device,
                    compute_type=compute_type,
                    **kw,
                )
                return model, None
            except Exception as exc:
                return None, str(exc)

        self._fw_auto_fallback = False
        self._fw_actual_device = self.asr_device
        self._fw_actual_compute_type = self.asr_compute_type

        if self.asr_device == "cuda":
            attempt_types: list[str] = []
            for ct in (self.asr_compute_type, "int8_float16", "int8"):
                if ct not in attempt_types:
                    attempt_types.append(ct)
            last_err = ""
            for ct in attempt_types:
                self._release_torch_cuda_memory_for_asr_gpu()
                model, err = load_whisper("cuda", ct)
                if model is not None:
                    self._fw_model = model
                    self._fw_actual_device = "cuda"
                    self._fw_actual_compute_type = ct
                    self._fw_auto_fallback = ct != self.asr_compute_type
                    self._fw_error = None
                    return
                last_err = err or last_err

            msg = last_err or "CUDA 上加载 Whisper 失败"
            if "Cannot find model" in msg or "No such file" in msg:
                msg = (
                    f"未找到faster-whisper模型[{self.asr_model_name}]，"
                    f"请先下载到data/model/ASR目录后重试。原始错误：{msg}"
                )
            if self.asr_auto_fallback_allowed and (
                self._looks_like_cuda_runtime_error(msg) or self._looks_like_cuda_oom(msg)
            ):
                model_cpu, err_cpu = load_whisper("cpu", "int8")
                if model_cpu is not None:
                    self._fw_model = model_cpu
                    self._fw_actual_device = "cpu"
                    self._fw_actual_compute_type = "int8"
                    self._fw_auto_fallback = True
                    self._fw_error = None
                    return
                self._fw_error = f"{msg}；CPU回退也失败：{err_cpu}"
                self._fw_model = None
                return
            self._fw_error = msg
            self._fw_model = None
            return

        model, err = load_whisper("cpu", self.asr_compute_type)
        if model is not None:
            self._fw_model = model
            self._fw_error = None
            return

        msg = err or ""
        if "Cannot find model" in msg or "No such file" in msg:
            msg = (
                f"未找到faster-whisper模型[{self.asr_model_name}]，"
                f"请先下载到data/model/ASR目录后重试。原始错误：{msg}"
            )
        if (
            self.asr_auto_fallback_allowed
            and self.asr_compute_type != "int8"
            and ("float16" in msg.lower() or "compute type" in msg.lower())
        ):
            model8, err8 = load_whisper("cpu", "int8")
            if model8 is not None:
                self._fw_model = model8
                self._fw_actual_compute_type = "int8"
                self._fw_auto_fallback = True
                self._fw_error = None
                return
            self._fw_error = f"{msg}；int8 回退失败：{err8}"
            self._fw_model = None
            return
        self._fw_error = msg
        self._fw_model = None

    def _ensure_voiceprint_extractor(self) -> None:
        if self._vp_extractor is not None or sherpa_onnx is None:
            return
        if not self.vp_model_path.exists():
            return
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(self.vp_model_path),
            debug=False,
            provider="cpu",
            num_threads=max(1, int(os.cpu_count() or 2) - 1),
        )
        self._vp_extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        if self.cache_voiceprint_path.exists():
            audio, sample_rate = sf.read(str(self.cache_voiceprint_path), dtype="float32", always_2d=True)
            self._vp_embedding_ref = self._extract_speaker_embedding(audio[:, 0], sample_rate)

    def _extract_speaker_embedding(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        stream = self._vp_extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=audio)
        stream.input_finished()
        emb = self._vp_extractor.compute(stream)
        return np.array(emb)

    def _verify_speaker(self, audio_file: Path) -> bool:
        if self.voiceprint_switch != "开启":
            return True
        if sherpa_onnx is None:
            return True
        if not self.cache_voiceprint_path.exists():
            return True
        self._ensure_voiceprint_extractor()
        if self._vp_extractor is None or self._vp_embedding_ref is None:
            return True
        try:
            audio, sample_rate = sf.read(str(audio_file), dtype="float32", always_2d=True)
        except Exception:
            # 非PCM wav等格式在声纹比对时直接跳过，避免阻塞主识别流程
            return True
        emb2 = self._extract_speaker_embedding(audio[:, 0], sample_rate)
        dot = float(np.dot(self._vp_embedding_ref, emb2))
        norm = float(np.linalg.norm(self._vp_embedding_ref) * np.linalg.norm(emb2))
        similarity = dot / norm if norm else 0.0
        return similarity >= self.voiceprint_threshold

    def _decode_audio_pcm_mono_av(self, audio_file: Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
        """将 webm/ogg 等解码为单声道 float32 PCM，供 sherpa 与时长判断使用（不可再返回全零占位）。"""
        if av is None:
            raise RuntimeError("需要 PyAV(av) 以读取浏览器上传的 webm/ogg")
        container = av.open(str(audio_file))
        try:
            astream = next((s for s in container.streams if s.type == "audio"), None)
            if astream is None:
                raise RuntimeError("文件中无音频轨")
            resampler = av.audio.resampler.AudioResampler(
                format="flt", layout="mono", rate=target_sr
            )
            chunks: list[np.ndarray] = []
            for frame in container.decode(astream):
                frame.pts = None
                for rf in resampler.resample(frame):
                    arr = rf.to_ndarray()
                    chunks.append(arr.flatten() if arr.ndim > 1 else arr)
            if not chunks:
                raise RuntimeError("解码后无采样数据")
            audio_1d = np.concatenate(chunks).astype(np.float32)
            return audio_1d, target_sr
        finally:
            container.close()

    def _read_audio_duration(self, audio_file: Path) -> tuple[np.ndarray, int, float]:
        try:
            audio, sample_rate = sf.read(str(audio_file), dtype="float32", always_2d=True)
            duration = len(audio) / float(sample_rate or 16000)
            return audio, sample_rate, duration
        except Exception:
            # 兼容浏览器 MediaRecorder 上传的 webm/ogg（此前误用全零波形导致 sherpa 无法识别）
            if av is not None:
                try:
                    audio_1d, sample_rate = self._decode_audio_pcm_mono_av(audio_file)
                    audio = audio_1d.reshape(-1, 1)
                    duration = len(audio_1d) / float(sample_rate)
                    return audio, sample_rate, duration
                except Exception:
                    pass
            raise

    def _recognize_with_sherpa(self, audio_file: Path) -> str:
        if sherpa_onnx is None:
            return "ASR服务不可用（未安装sherpa_onnx）"
        self._ensure_recognizer()
        if self._recognizer is None:
            detail = f"（{self._recognizer_error}）" if self._recognizer_error else ""
            return f"ASR模型初始化失败{detail}"
        try:
            audio, sample_rate, duration = self._read_audio_duration(audio_file)
        except Exception:
            return "ASR音频读取失败（请使用wav或切换faster_whisper_cuda引擎）"
        if duration < MIN_UPLOAD_AUDIO_SEC:
            return ""
        if not self._verify_speaker(audio_file):
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio[:, 0])
        self._recognizer.decode_stream(stream)
        raw = json.loads(str(stream.result))
        emotion_key = raw.get("emotion", "").strip("<|>")
        event_key = raw.get("event", "").strip("<|>")
        text = raw.get("text", "")
        emotion_dict = {
            "HAPPY": "[开心]",
            "SAD": "[伤心]",
            "ANGRY": "[愤怒]",
            "DISGUSTED": "[厌恶]",
            "SURPRISED": "[惊讶]",
            "NEUTRAL": "",
            "EMO_UNKNOWN": "",
        }
        event_dict = {
            "BGM": "",
            "Applause": "[鼓掌]",
            "Laughter": "[大笑]",
            "Cry": "[哭]",
            "Sneeze": "[打喷嚏]",
            "Cough": "[咳嗽]",
            "Breath": "[深呼吸]",
            "Speech": "",
            "Event_UNK": "",
        }
        result = event_dict.get(event_key, "") + text + emotion_dict.get(emotion_key, "")
        if result == "The.":
            return ""
        return result

    def _recognize_with_faster_whisper(self, audio_file: Path) -> str:
        if WhisperModel is None:
            return "ASR服务不可用（未安装faster-whisper）"
        _, _, duration = self._read_audio_duration(audio_file)
        if duration < MIN_UPLOAD_AUDIO_SEC:
            return ""
        if not self._verify_speaker(audio_file):
            return ""
        self._ensure_fw_model()
        if self._fw_model is None:
            detail = f"（{self._fw_error}）" if self._fw_error else ""
            return f"ASR模型初始化失败{detail}"
        try:
            segments, _ = self._fw_model.transcribe(
                str(audio_file),
                beam_size=1,
                vad_filter=True,
                language="zh",
                condition_on_previous_text=False,
            )
            text = "".join(segment.text for segment in segments).strip()
            if text in {"", "The.", "."} and self.asr_auto_fallback_allowed:
                # VAD 过严或首段过短时，再试关闭 VAD（仍由 Whisper 自判语音）
                segments2, _ = self._fw_model.transcribe(
                    str(audio_file),
                    beam_size=1,
                    vad_filter=False,
                    language="zh",
                    condition_on_previous_text=False,
                )
                text = "".join(segment.text for segment in segments2).strip()
            if text in {"", "The.", "."}:
                return ""
            self._fw_error = None
            return text
        except Exception as e:
            self._fw_error = str(e)
            return f"ASR识别失败（{e}）"

    def recognize_file(self, audio_file: Path) -> str:
        self._sync_runtime_fields()
        if self.asr_engine == "sherpa_local":
            res = self._recognize_with_sherpa(audio_file)
            if self.asr_auto_fallback_allowed and (
                res.startswith("ASR模型初始化失败") or res.startswith("ASR服务不可用")
            ):
                fw = self._recognize_with_faster_whisper(audio_file)
                if fw and not fw.startswith("ASR模型初始化失败") and not fw.startswith("ASR服务不可用"):
                    return fw
            return res
        if self.asr_engine == "faster_whisper_cuda":
            res = self._recognize_with_faster_whisper(audio_file)
            if self.asr_auto_fallback_allowed and (
                res.startswith("ASR模型初始化失败") or res.startswith("ASR识别失败")
            ):
                fallback = self._recognize_with_sherpa(audio_file)
                if fallback and not fallback.startswith("ASR模型初始化失败") and not fallback.startswith("ASR服务不可用"):
                    return fallback
            return res
        return self._recognize_with_sherpa(audio_file)

    def get_runtime_status(self) -> dict[str, Any]:
        self._sync_runtime_fields()
        physical_cuda_idx = os.environ.get("VIRTMATE_ASR_CUDA_DEVICE_PHYSICAL")
        return {
            "engine": self.asr_engine,
            "model": self.asr_model_name,
            "device": self.asr_device,
            "compute_type": self.asr_compute_type,
            "actual_device": self._fw_actual_device,
            "actual_compute_type": self._fw_actual_compute_type,
            "auto_fallback": self._fw_auto_fallback,
            "auto_fallback_allowed": self.asr_auto_fallback_allowed,
            "cuda_device_index_config": self.asr_gpu_index_cfg,
            "cuda_device_index_effective": (
                self._cuda_device_index() if self._fw_actual_device == "cuda" else None
            ),
            "cuda_device_index_physical": (
                int(physical_cuda_idx) if physical_cuda_idx and physical_cuda_idx.isdigit() else None
            ),
            "cuda_device_order": os.environ.get("CUDA_DEVICE_ORDER"),
            "voiceprint_switch": self.voiceprint_switch,
            "voiceprint_threshold": self.voiceprint_threshold,
            "sherpa_ready": self._recognizer is not None,
            "faster_whisper_ready": self._fw_model is not None,
            "last_error": self._fw_error or self._recognizer_error,
        }
