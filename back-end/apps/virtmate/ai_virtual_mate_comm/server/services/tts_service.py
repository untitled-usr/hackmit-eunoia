from __future__ import annotations

import asyncio
import contextlib
import uuid
import wave
from pathlib import Path
from typing import Any

import requests as rq

try:
    import edge_tts
except Exception:  # pragma: no cover
    edge_tts = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from server.config import RuntimeConfig


class TtsService:
    def __init__(self, runtime: RuntimeConfig) -> None:
        self.runtime = runtime
        self.audio_dir = runtime.data_dir / "cache" / "server_audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.edge_speaker_mapping = {
            "晓艺-年轻女声": "zh-CN-XiaoyiNeural",
            "晓晓-成稳女声": "zh-CN-XiaoxiaoNeural",
            "云健-大型纪录片男声": "zh-CN-YunjianNeural",
            "云希-短视频热门男声": "zh-CN-YunxiNeural",
            "云夏-年轻男声": "zh-CN-YunxiaNeural",
            "云扬-成稳男声": "zh-CN-YunyangNeural",
            "晓北-辽宁话女声": "zh-CN-liaoning-XiaobeiNeural",
            "晓妮-陕西话女声": "zh-CN-shaanxi-XiaoniNeural",
            "晓佳-粤语成稳女声": "zh-HK-HiuGaaiNeural",
            "晓满-粤语年轻女声": "zh-HK-HiuMaanNeural",
            "云龙-粤语男声": "zh-HK-WanLungNeural",
            "晓辰-台湾话年轻女声": "zh-TW-HsiaoChenNeural",
            "晓宇-台湾话成稳女声": "zh-TW-HsiaoYuNeural",
            "云哲-台湾话男声": "zh-TW-YunJheNeural",
            "佳太-日语男声": "ja-JP-KeitaNeural",
            "七海-日语女声": "ja-JP-NanamiNeural",
        }
        self._last_error: str | None = None

    def _get_local_tts_runtime(self) -> dict[str, Any]:
        # 兼容旧 key，同时支持新 key
        local_ip = self.runtime.more_set.get("本地TTS服务器IP", self.runtime.more_set.get("local_tts_host", "127.0.0.1"))
        timeout_sec = int(self.runtime.more_set.get("本地TTS超时时间秒", "180"))
        gpt_port = str(self.runtime.more_set.get("GPT-SoVITS端口", "9880"))
        cosy_port = str(self.runtime.more_set.get("CosyVoice端口", self.runtime.more_set.get("cosyvoice_port", "9881")))
        index_port = str(self.runtime.more_set.get("Index-TTS端口", self.runtime.more_set.get("indextts_port", "9884")))
        voxcpm_port = str(self.runtime.more_set.get("VoxCPM端口", self.runtime.more_set.get("voxcpm_port", "9885")))
        fallback_engine = str(self.runtime.more_set.get("本地TTS失败回退引擎", "云端edge-tts"))
        return {
            "local_ip": local_ip,
            "timeout_sec": timeout_sec,
            "gpt_port": gpt_port,
            "cosy_port": cosy_port,
            "index_port": index_port,
            "voxcpm_port": voxcpm_port,
            "fallback_engine": fallback_engine,
        }

    async def synthesize(self, text: str, tts_engine: str | None = None) -> dict[str, Any]:
        engine = tts_engine or self.runtime.config.get("语音合成引擎", "云端edge-tts")
        return await self._synthesize_by_engine(engine, text)

    async def _synthesize_by_engine(self, engine: str, text: str) -> dict[str, Any]:
        if engine == "关闭语音合成":
            return {"audio_url": "", "engine": engine, "duration": 0.0, "filename": ""}
        if engine == "云端edge-tts":
            return await self._edge_tts(text)
        if engine == "云端Paddle-TTS":
            return await self._paddle_tts(text)
        if engine == "自定义API-TTS":
            return await self._custom_tts(text)
        if engine in {"本地GPT-SoVITS", "本地CosyVoice", "本地Index-TTS", "本地VoxCPM"}:
            local_res = await self._local_http_tts(engine, text)
            if not local_res.get("error"):
                return local_res
            fallback_engine = self._get_local_tts_runtime()["fallback_engine"]
            if fallback_engine and fallback_engine not in {engine, "关闭语音合成"}:
                fallback_res = await self._synthesize_by_engine(fallback_engine, text)
                fallback_res["fallback_from"] = engine
                fallback_res["fallback_reason"] = local_res["error"]
                return fallback_res
            return local_res
        return {"audio_url": "", "engine": engine, "duration": 0.0, "filename": "", "error": f"未适配的TTS引擎: {engine}"}

    async def _edge_tts(self, text: str) -> dict[str, Any]:
        if edge_tts is None:
            return {"audio_url": "", "engine": "云端edge-tts", "duration": 0.0, "filename": "", "error": "未安装edge-tts"}
        speaker_name = self.runtime.config.get("edge-tts音色", "晓艺-年轻女声")
        speaker = self.edge_speaker_mapping.get(speaker_name, "zh-CN-XiaoyiNeural")
        rate = self.runtime.config.get("edge-tts语速", "+0")
        pitch = self.runtime.config.get("edge-tts音高", "+10")
        filename = f"{uuid.uuid4().hex}.mp3"
        path = self.audio_dir / filename
        communicate = edge_tts.Communicate(text, speaker, rate=f"{rate}%", pitch=f"{pitch}Hz")
        await communicate.save(str(path))
        return {
            "audio_url": f"/api/audio/{filename}",
            "engine": "云端edge-tts",
            "duration": self._estimate_audio_duration(path),
            "filename": filename,
        }

    async def _paddle_tts(self, text: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._paddle_tts_sync, text)

    def _paddle_tts_sync(self, text: str) -> dict[str, Any]:
        lang_mapping = {"中文": "zh", "英语": "uk", "日语": "jp"}
        lang = lang_mapping.get(self.runtime.config.get("PaddleTTS语言", "中文"), "kor")
        rate = self.runtime.config.get("PaddleTTS语速", "5")
        url = f"https://fanyi.baidu.com/gettts?lan={lang}&spd={rate}&text={text}"
        res = rq.get(url, timeout=120)
        filename = f"{uuid.uuid4().hex}.mp3"
        path = self.audio_dir / filename
        path.write_bytes(res.content)
        return {
            "audio_url": f"/api/audio/{filename}",
            "engine": "云端Paddle-TTS",
            "duration": self._estimate_audio_duration(path),
            "filename": filename,
        }

    async def _custom_tts(self, text: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._custom_tts_sync, text)

    def _custom_tts_sync(self, text: str) -> dict[str, Any]:
        custom_file = self.runtime.data_dir / "set" / "custom_tts_set.txt"
        lines = custom_file.read_text(encoding="utf-8").splitlines()
        custom_url = lines[1].strip() if len(lines) > 1 else ""
        custom_model = lines[4].strip() if len(lines) > 4 else ""
        custom_voice = lines[7].strip() if len(lines) > 7 else ""
        custom_key = lines[10].strip() if len(lines) > 10 else ""
        if OpenAI is None:
            return {"audio_url": "", "engine": "自定义API-TTS", "duration": 0.0, "filename": "", "error": "未安装openai依赖"}
        filename = f"{uuid.uuid4().hex}.mp3"
        path = self.audio_dir / filename
        client = OpenAI(api_key=custom_key, base_url=custom_url)
        with client.audio.speech.with_streaming_response.create(
            model=custom_model,
            voice=custom_voice,
            input=text,
            response_format="mp3",
        ) as response:
            response.stream_to_file(str(path))
        return {
            "audio_url": f"/api/audio/{filename}",
            "engine": "自定义API-TTS",
            "duration": self._estimate_audio_duration(path),
            "filename": filename,
        }

    async def _local_http_tts(self, engine: str, text: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._local_http_tts_sync, engine, text)

    def _local_http_tts_sync(self, engine: str, text: str) -> dict[str, Any]:
        runtime = self._get_local_tts_runtime()
        local_ip = runtime["local_ip"]
        timeout_sec = runtime["timeout_sec"]
        try:
            if engine == "本地GPT-SoVITS":
                prompt = self.runtime.more_set.get("GPT-SoVITS参考音频文本", "")
                prompt_lang = self.runtime.more_set.get("GPT-SoVITS参考音频语言", "zh")
                out_lang = self.runtime.more_set.get("GPT-SoVITS合成输出语言", "zh")
                ref_audio = self.runtime.more_set.get("GPT-SoVITS参考音频路径(位于GSV整合包内)", "example.wav")
                url = (
                    f"http://{local_ip}:{runtime['gpt_port']}/tts?text={text}&text_lang={out_lang}&prompt_text={prompt}"
                    f"&prompt_lang={prompt_lang}&ref_audio_path={ref_audio}"
                )
            elif engine == "本地CosyVoice":
                url = f"http://{local_ip}:{runtime['cosy_port']}/cosyvoice/?text={text}"
            elif engine == "本地Index-TTS":
                url = f"http://{local_ip}:{runtime['index_port']}/indextts/?text={text}"
            else:
                url = f"http://{local_ip}:{runtime['voxcpm_port']}/voxcpm/?text={text}"
            res = rq.get(url, timeout=timeout_sec)
            res.raise_for_status()
            filename = f"{uuid.uuid4().hex}.wav"
            path = self.audio_dir / filename
            path.write_bytes(res.content)
            self._last_error = None
            return {
                "audio_url": f"/api/audio/{filename}",
                "engine": engine,
                "duration": self._estimate_audio_duration(path),
                "filename": filename,
            }
        except Exception as e:
            self._last_error = str(e)
            return {
                "audio_url": "",
                "engine": engine,
                "duration": 0.0,
                "filename": "",
                "error": f"{engine}调用失败：{e}",
            }

    @staticmethod
    def _estimate_audio_duration(path: Path) -> float:
        suffix = path.suffix.lower()
        if suffix != ".wav":
            # 对 mp3 不做复杂依赖解析，按经验值回传0，前端以onended为准
            return 0.0
        try:
            with contextlib.closing(wave.open(str(path), "rb")) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                if rate == 0:
                    return 0.0
                return round(frames / float(rate), 3)
        except Exception:
            return 0.0

    def get_runtime_status(self) -> dict[str, Any]:
        runtime = self._get_local_tts_runtime()
        return {
            "local_ip": runtime["local_ip"],
            "gpt_sovits_port": runtime["gpt_port"],
            "cosyvoice_port": runtime["cosy_port"],
            "indextts_port": runtime["index_port"],
            "voxcpm_port": runtime["voxcpm_port"],
            "timeout_sec": runtime["timeout_sec"],
            "fallback_engine": runtime["fallback_engine"],
            "last_error": self._last_error,
        }

